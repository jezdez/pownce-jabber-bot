import re
import pownce

from twisted.python import log
from twisted.words.protocols.jabber.jid import JID
from powncebot.bot.accounts import User, login

DEFAULT_STATUS = 'Send stuff! (or HELP for more information)'
URL_RE = re.compile(r'^https?://\S+$')
GREETINGS = ('hi', 'hello', 'good day', 'hey', 'howdy', 'yo')

class Command(object):
    """Abstract base command that shows how commands are structered"""
    def __init__(self, parent, message):
        self.parent = parent
        self.message = message
        self.aliases = ()
        self.jid = JID(self.message['from']).userhost()
    
    def guide(self):
        self.send("Usage: %s %s" % (self.__class__.__name__, self.usage))

    def send(self, reply):
        self.parent.reply(self.message["from"], reply)

    def log(self, text):
        log.msg(text)

    def valid_to(self, to):
        for option in ('@public', '@all', '@friend_', '@set_'):
            if to.startswith(option):
                return True
        return False


class unknown(Command):
    """Unknown command. Type "help" for available commands."""

    def __init__(self, parent, message, *args):
        Command.__init__(self, parent, message)

        self.send(self.__class__.__doc__)


class help(Command):
    """Sends back help about the given command(s)."""

    usage = "COMMAND [...]"

    def __init__(self, parent, message, *commands):
        Command.__init__(self, parent, message)

        self.commands = commands
        self.aliases = ('wtf', 'howto')
        
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

    def __init__(self, parent, message, *credentials):
        Command.__init__(self, parent, message)

        self.credentials = credentials
        self.aliases = ('signup', 'login', 'logon')

        if len(self.credentials) != 2:
            return self.guide()
        username, password = self.credentials[0:2]

        if self.parent.session.query(User).filter_by(jid=self.jid).count():
            return self.send("Your Jabber account %s is already registered "
                        "with the Pownce account %s!" % (self.jid, username))
        try:
            api = login(username, password)
        except pownce.AuthenticationRequired:
            self.send("Username and password do not match. Please try again.")
        else:
            user = User(username, password, self.jid)
            self.parent.session.save(user)
            self.parent.session.commit()
            self.log("REGISTER: user %s (%s) created" % (username, self.jid))
            self.send("Your Jabber account %s and your Pownce account %s are "
                "now registered at this Jabber bot." % (self.jid, username))


class unregister(Command):
    """Unregisters a Pownce account with this jabber bot."""

    usage = "PASSWORD"

    def __init__(self, parent, message, *credentials):
        Command.__init__(self, parent, message)

        self.credentials = credentials
        self.aliases = ('logoff', 'signoff')

        if len(self.credentials) != 1:
            return self.guide()
        password = self.credentials[0]

        user = self.parent.session.query(User).filter_by(jid=self.jid).first()
        if user:
            if user.password != password:
                return self.send("Supplied password is wrong.")
            try:
                self.parent.session.delete(user)
                self.parent.session.commit()
            except:
                pass
            self.log("UNREGISTER: user %s created" % self.jid)
            self.send("Your Jabber account %s is now unregistered!" % self.jid)
        else:
            self.send("You have no Pownce account registered under you Jabber "
                      "ID %s" % self.jid)


class message(Command):
    "Posts a message. Optional: SEND_TO (@public, @all or @friend_<username>)."
    
    usage = "[SEND_TO] NOTE"
    
    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)
        
        self.text = text
        self.aliases = ('note', 'msg')
        
        if not text:
            return self.guide()

        user = self.parent.session.query(User).filter_by(jid=self.jid).first()
        if user:
            try:
                api = login(user.username, user.password)
                # if self.valid_to(text[0]):
                #     text = text[1:]
                #     to = to[1:]
                # else:
                #     to = api.send_to_default()
                body = text[1:]
                to = "friend_" + text[0][1:]
                print to, body
                reply = api.post_message(to, " ".join(body))
                if reply:
                    return self.send("You message has been posted.")
                    self.log("MESSAGE: %s wrote '%s'" % (user.username, body))
            except pownce.AuthenticationRequired:
                return self.send("Username and password do not match "
                            "(anymore). Please re-register with this bot.")
            except pownce.PrivacyViolation:
                return self.send("You are not allowed to do this.")
            except pownce.NotFound:
                return self.send("The user or note could not be handled.")
            except:
                raise
                return self.send("Something went wrong. Try again.")
        else:
            return self.send("Please register your Pownce account first.")


##### Hier weiter machen ### TODO
# class link(Command):
#     "Posts a link. Optional: NOTE, SEND_TO (@public, @all or @friend_<username>)."
# 
#     usage = "[SEND_TO] URL [NOTE]"
# 
#     def __init__(self, parent, message, *text):
#         Command.__init__(self, parent, message)
# 
#         self.text = text
#         self.aliases = ('url',)
# 
#         if not text:
#             return self.guide()
# 
##### Ab hier alter Kram
#     url = text[0]
#     if not URL_RE.search(url):
#         return "A valid URL is required."
#     
#     body = text[1:-1]
#     receiver = ALLOWED_RECEIVERS.get(text[-1], None)
#     if receiver is None:
#         body = text[1:]
#     try:
#         user = User.objects.get(jid=mess.getFrom().__str__())
#     except User.DoesNotExist:
#         return "Please register your Pownce account first."
#     else:
#         self.log("link: new link from %s: %s %s" % (user.username, body, url))
#         self.send(mess.getFrom(), "Posting link..", mess)
#         Note.objects.create(user=user, body=" ".join(body), typ="link", link=url, to=receiver)
# cmd_link.usage = ""
# cmd_link.alias = ('url',)
# 


class about(Command):
    "Sends an about message."

    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)

        return self.send("I'm a jabber bot. My creator is jezdez.")


class greeting(Command):
    "Sends a greeting."
    
    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)
        
        self.aliases = GREETINGS
        return self.send(random.choice(GREETINGS).capitalize()+"!")


class ping(Command):
    "Sends a pong."

    def __init__(self, parent, message, *text):
        Command.__init__(self, parent, message)

        return self.send("pong")
