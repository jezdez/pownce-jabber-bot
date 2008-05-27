import re
import random

from twisted.python import log
from twisted.words.protocols.jabber.jid import JID

from powncebot import accounts, settings

URL_RE = re.compile(r'^https?://\S+$')

from pownce import PrivacyViolation, NotFound, AuthenticationRequired, ServerError

class GuidanceNeeded(Exception):
    pass

class UserAlreadyExists(Exception):
    pass

class UserDoesNotExist(Exception):
    pass

class Command(object):
    """Abstract base command that shows how commands are structered"""
    
    aliases = ()
    
    def __init__(self, parent, message):
        self.parent = parent
        self.message = message
        self.jid = JID(self.message['from']).userhost()
    
    def guide(self):
        """
        Thou shalt be guided by this magic inscription.
        """
        self.send("Usage: %s %s" % (self.__class__.__name__, self.usage))

    def send(self, reply):
        """
        Sends a mystical message back in the xmlstream.
        """
        self.parent.reply(self.message["from"], reply)

    def log(self, text):
        """
        Wow, logging.
        """
        log.msg(text)

    def handle_to(self, to, api):
        """
        Handles the recipient by looking for the allowed strings and loading
        the user information if needed.
        """
        for option in ('@public', '@all', '@friend_', '@set_'):
            if to.startswith(option):
                return to[1:]
        # in case someone uses @<username> to send a direct message:
        if to.startswith('@'):
            if len(to) > 1:
                try:
                    user = api.get_user(to[1:])
                except:
                    raise
                return 'friend_%s' % user.raw_user_dict['id']
            else:
                raise GuidanceNeeded
        return None

    def login(self, username, password):
        """
        Tries to login to pownce.com with the given credentials and return
        an api and a user object if successful.
        """
        api = accounts.Api(username, password, settings.APPLICATION_KEY)
        try:
            user = api.get_user(username)
        except:
            raise AuthenticationRequired
        else:
            return api


class unknown(Command):
    """Unknown command. Type "help" for available commands."""

    def __init__(self, parent, message, *args):
        Command.__init__(self, parent, message)

        self.send(self.__class__.__doc__)


class help(Command):
    """Sends back help about the given command(s)."""

    usage = "COMMAND [...]"
    aliases = ('wtf', 'howto')

    def __init__(self, parent, message, *commands):
        Command.__init__(self, parent, message)

        self.commands = commands
        
        if self.commands:
            usage_commands = []
            for command in self.commands:
                command_class = self.parent.getCommand(command)
                if hasattr(command_class, "usage"):
                    usage_commands.append(
                        "Usage: %s %s\n" % (command, command_class.usage))
                usage_commands.append(command_class.__doc__ or "")
            usage_commands.reverse()
            self.send("\n".join(usage_commands))
        else:
            self.send(
                "This is a Pownce jabber bot. "
                "Available commands:\n\n%s" % self.parent.help)


class register(Command):
    """Registers a Pownce account with this jabber bot."""

    usage = "USERNAME PASSWORD"
    aliases = ('signup', 'login', 'logon')

    def __init__(self, parent, message, *credentials):
        Command.__init__(self, parent, message)

        self.credentials = credentials

        try:
            if len(self.credentials) != 2:
                raise GuidanceNeeded

            username, password = self.credentials[0:2]

            if self.parent.session.query(accounts.User).filter_by(jid=self.jid).count():
                raise UserAlreadyExists

            api = self.login(username, password)

        except AuthenticationRequired:
            self.send("Username and password do not match. Please try again.")

        except UserAlreadyExists:
            self.send ("Your Jabber account %s is already registered "
                "with the Pownce account %s!" % (self.jid, username))

        except GuidanceNeeded:
            self.guide()

        except:
            self.log("FAILED: creating user %s (%s)" % (username, self.jid))
            self.send("Something went wrong. Try again.")

        else:
            user = accounts.User(username, password, self.jid)
            self.parent.session.save(user)
            self.parent.session.commit()
            self.log("REGISTER: user %s (%s) created" % (username, self.jid))
            self.send("Your Jabber account %s and your Pownce account %s are "
                "now registered at this Jabber bot." % (self.jid, username))

class unregister(Command):
    """Unregisters a Pownce account with this jabber bot."""

    usage = "PASSWORD"
    aliases = ('logoff', 'signoff')

    def __init__(self, parent, message, *credentials):
        Command.__init__(self, parent, message)

        self.credentials = credentials

        try:
            if len(self.credentials) != 1:
                raise GuidanceNeeded

            user = self.parent.session.query(accounts.User).filter_by(jid=self.jid).first()
            if not user:
                raise UserDoesNotExist

            password = self.credentials[0]

            if user.password != password:
                raise AuthenticationRequired

            self.parent.session.delete(user)
            self.parent.session.commit()

        except AuthenticationRequired:
            self.send("Supplied password is wrong.")

        except UserDoesNotExist:
            self.send("You have no Pownce account registered under the "
                "Jabber ID %s" % self.jid)

        except GuidanceNeeded:
            self.guide()

        except:
            self.log("FAILED: unregistering user %s" % self.jid)
            self.send("Unregistering was not successful. Try again.")

        else:
            self.log("UNREGISTER: user %s created" % self.jid)
            self.send("Your Jabber account %s is now unregistered!" % self.jid)

class message(Command):
    "Posts a message. Optional: SEND_TO (@public, @all, @set_<NAME> or @<username>)."
    
    usage = "[SEND_TO] NOTE"
    aliases = ('note', 'msg')
    
    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)
        
        try:
            if not text:
                raise GuidanceNeeded
            user = self.parent.session.query(accounts.User).filter_by(jid=self.jid).first()
            if not user:
                raise UserDoesNotExist
            self.text = text
            api = self.login(user.username, user.password)
            to = self.handle_to(text[0], api)
            if to is None:
                to = api.send_to_default()
            else:
                text = text[1:]
            
            if not text:
                raise GuidanceNeeded
            
            reply = api.post_message(to, " ".join(text))

        except UserDoesNotExist:
            self.send("Please register your Pownce account first.")

        except PrivacyViolation:
            self.send("You are not allowed to do this.")

        except NotFound:
            self.send("The recipient could not be found or the note "
                "could not be handled. Try again.")

        except AuthenticationRequired:
            self.send("Username and password do not match (anymore). "
                "Please re-register with this bot.")

        except ServerError:
            self.send("Pownce is having a nap. Try again later.")

        except GuidanceNeeded:
            self.guide()

        except:
            self.log("FAILED: user %s sending the message: %s" % (self.jid, self.text))
            self.send("Something went wrong. Try again.")

        else:
            self.log("MESSAGE: %s wrote '%s'" % (user.username, text))
            self.send("You message has been posted.")


class link(Command):
    "Posts a link. Optional: NOTE, SEND_TO (@public, @all, @set_<NAME> or @<username>)."

    usage = "[SEND_TO] URL [NOTE]"
    aliases = ('url',)

    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)

        try:
            user = self.parent.session.query(accounts.User).filter_by(jid=self.jid).first()
            if not user:
                raise UserDoesNotExist
            if not text:
                raise GuidanceNeeded

            self.text = text
            api = self.login(user.username, user.password)
            to = self.handle_to(text[0], api)
            if to is None:
                to = api.send_to_default()
            else:
                text = text[1:]

            if not text:
                raise GuidanceNeeded
            url = text[0]
            if not URL_RE.search(url):
                return self.send("A valid URL is required.")
            
            if len(text) > 1:
                body = text[1:]
                if body[0] == "[%s]" % url: # weird iChat bug
                    body = body[1:]
            else:
                body = ('',)
            print body
            reply = api.post_link(to, url, " ".join(body))

        except GuidanceNeeded:
            self.guide()

        except PrivacyViolation:
            self.send("You are not allowed to do this.")

        except NotFound:
            self.send("The user or note could not be handled.")

        except AuthenticationRequired:
            self.send("Username and password do not match (anymore). "
                "Please re-register with this bot.")

        except ServerError:
            self.send("ServerError")

        except UserDoesNotExist:
            self.send("Please register your Pownce account first.")

        except:
            self.send("Something went wrong. Check if the URL is valid and "
                "then try again.")

        else:
            self.log("LINK: %s posted '%s'" % (user.username, url))
            self.send("Your link has been posted.")


class about(Command):
    "Sends an about message."

    aliases = ('author', 'contact')

    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)

        return self.send("I'm a jabber bot. My creator is jezdez.")


class greeting(Command):
    "Sends a greeting."
    
    aliases = (
        "hi",
        "oi",
        "yo",
        "hei",
        "hej",
        "hey",
        "ahoi",
        "ahoj",
        "tach",
        "aloha",
        "hallo",
        "hello",
        "howdy",
        "salam",
        "salut",
        "ni hao",
        "servus",
        "shalom",
        "bonjour",
        "merhaba",
        "namaste",
    )

    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)
        return self.send(random.choice(greeting.aliases).capitalize()+"!")


class ping(Command):
    "Sends an answer as fast as possible. a.k.a. ping."

    def __init__(self, parent, message, *args):
        Command.__init__(self, parent, message)

        return self.send("pong")
