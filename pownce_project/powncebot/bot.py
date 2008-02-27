#!/usr/bin/python
import os
import re
import time
import xmpp
import random
import inspect
import logging
import optparse

from django.utils.daemonize import become_daemon
from django.dispatch import dispatcher
from django.conf import settings
from django.core import management

# relative import because of weird double signaling of post_save signal 
from powncebot.models import User, Note, pownce_login, ALLOWED_RECEIVERS, APP_PATH
from powncebot.signals import post_message_sent

URL_RE = re.compile(r'^https?://\S+$')
DEFAULT_STATUS = 'Send stuff! (or HELP for more information)'
GREETINGS = ('hi', 'hello', 'good day', 'hey', 'howdy', 'yo')
HELP_COMMANDS = ('register', 'unregister', 'link', 'message', 'help')

LOG_FILE = os.path.join(APP_PATH, 'logs/bot.log')
LOG_FORMAT = '%(asctime)s %(message)s'
LOG_LEVEL = logging.DEBUG
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, filename=LOG_FILE, filemode='a')

class PownceJabberBot(object):
    """This is a Pownce jabber bot."""
    command_prefix = 'cmd_'

    def __init__(self, jid, password, res=None, use_daemon=False):
        self.jid = xmpp.JID(jid)
        self.password = password
        self.res = (res or self.__class__.__name__)
        self.conn = None
        self._finished = False
        self._restarted = False

        self.use_daemon = use_daemon
        self.admins = [email for name, email in settings.ADMINS]

        self.commands = {}
        for (name, method) in inspect.getmembers(self):
            if inspect.ismethod(method) and name.startswith(self.command_prefix):
                self.commands[name[len(self.command_prefix):]] = method
                if hasattr(method, "alias"):
                    for alias in method.alias:
                        self.commands[alias] = method

        self.help_text = self.__doc__.strip() + "Type one of the following commands:\n"
        self.help_text += " ".join(["\n%s %s" % (command, method.usage) for command, method in self.commands.items() if hasattr(method, 'usage') and command in HELP_COMMANDS])

    def log(self, text):
        """Logging facility."""
        logging.info(text)

    def resolve_command(self, cmd):
        return self.commands.get(cmd, self.unknown)

    def connect(self):
        if not self.conn:
            conn = xmpp.Client(self.jid.getDomain(), debug = [])

            if not conn.connect():
                self.log('unable to connect to server.')
                return None

            if not conn.auth(self.jid.getNode(), self.password, self.res):
                self.log('unable to authorize with server.')
                return None

            conn.RegisterHandler('message', self.callback_message)
            conn.RegisterHandler('presence', self.callback_presence)
            conn.sendInitPresence()
            self.conn = conn
        return self.conn

    def quit(self):
        """Stop serving messages and exit."""
        self._finished = True

    def send(self, user, text, in_reply_to = None):
        """Sends a simple message to the specified user."""
        mess = xmpp.Message(user, text)
        if in_reply_to:
            mess.setThread(in_reply_to.getThread())
            mess.setType(in_reply_to.getType())
        self.connect().send(mess)

    def callback_message(self, conn, mess):
        """Messages sent to the bot will arrive here. Command handling + routing is done in this function."""
        text = mess.getBody()

        # If a message format is not supported (eg. encrypted), txt will be None
        if not text:
            return

        if ' ' in text:
            command, args = text.split(' ',1)
        else:
            command, args = text,''

        cmd = command.lower()
        args = args.strip().split()
        reply = self.resolve_command(cmd)(mess, *args)
        if reply:
            self.send(mess.getFrom(), reply, mess)

    def callback_presence(self, conn, pres):
        """Presence changes of clients will arrive here. Automatic authorizing and unauthorizing here."""
        presence_type = pres.getType()
        roster = self.conn.getRoster()
        try:
            roster.Authorize(pres.getFrom())
        except:
            pass

    def connected(self):
        self.set_status()
    
    def disconnected(self):
        if self._restarted:
            self._restarted = False
            management.call_command('runbot', daemon=self.use_daemon)
            self.log('bot restarted.')
    
    def set_status(self, status_text=DEFAULT_STATUS):
        if self.conn and self.conn.isConnected():
            self.conn.send(xmpp.Presence(status=status_text, show='chat'))

    def serve_forever(self):
        """Connects to the server and handles messages."""
        if self.connect():
            self.log('bot connected. serving forever.')
            self.connected()
        else:
            self.log('could not connect to server - aborting.')
            return

        try:
            while not self._finished:
                if self.conn and self.conn.isConnected():
                    self.conn.Process(1)
                else:
                    self.conn = None
                    self.connect()
                    time.sleep(5)
        except KeyboardInterrupt:
            self.log('bot stopped by user request. shutting down.')

        self.disconnected()

    def unknown(self, *args):
        return 'Unknown command. Type "help" for available commands.'

    def cmd_help(self, mess, *commands):
        """Sends back help about the given command(s)."""
        if not commands:
            return self.help_text
        else:
            usage_commands = []
            for command in commands:
                method = self.resolve_command(command)
                if method == self.unknown:
                    return self.unknown()
                if hasattr(method, "usage"):
                    usage_commands.append("\nUsage: %s %s" % (command, method.usage))
                if hasattr(method, "__doc__"):
                    usage_commands.append(method.__doc__ or '')
            usage_commands.reverse()
            return '\n'.join(usage_commands)
    cmd_help.usage = "COMMAND [...]"

    def only_admin(function):
        "admins only decorator"
        def _inner_func(self, mess, *args):
            if xmpp.JID(mess.getFrom()).getStripped() in self.admins:
                return function(self, mess, *args)
            else:
                return self.unknown()
        return _inner_func

    #@only_admin
    def cmd_quit(self, mess, *args):
        self.quit()
        return 'quitting..'
    cmd_quit = only_admin(cmd_quit)
    
    #@only_admin
    def cmd_restart(self, mess, *args):
        self._restarted = True
        self.quit()
        return 'restarting..'
    cmd_restart = only_admin(cmd_restart)

    #@only_admin
    def cmd_status(self, mess, *args):
        status = " ".join(args)
        self.set_status(status)
        return 'status set to: %s' % status
    cmd_status = only_admin(cmd_status)

    def cmd_register(self, mess, *credentials):
        "Registers a Pownce account with this jabber bot."
        if len(credentials) != 2:
            return self.cmd_help(mess, "register")
        username, password = credentials[0:2]
        jid = mess.getFrom().__str__()
        try:
            user = User.objects.get(jid=jid)
        except User.DoesNotExist:
            self.send(mess.getFrom(), "Just a moment please.", mess)
            if not pownce_login(username, password):
                return 'Supplied username and password do not match. Try again.'
            user = User.objects.create(username=username, password=password, jid=jid)
            self.log('register: new user %s (%s) created' % (username, jid))
            return 'Your Jabber account %s and your Pownce account %s are now registered at this Jabber bot.' % (jid, username)
        else:
            return 'Your Jabber account %s is already registered with the Pownce account %s!' % (jid, username)
    cmd_register.usage = "USERNAME PASSWORD"
    cmd_register.alias = ('logon', 'login')

    def cmd_unregister(self, mess, *credentials):
        "Unregisters a Pownce account with this jabber bot."
        if len(credentials) != 1:
            return self.cmd_help(mess, "unregister")
        password = credentials[0]
        jid = mess.getFrom().__str__()
        try:
            user = User.objects.get(jid=jid)
        except User.DoesNotExist:
            self.log('unregister: failed try of jid %s' % jid)
            return "You have no Pownce account registered under you Jabber ID %s" % jid
        else:
            if user.password != password:
                return "Supplied password is wrong."
            self.log('unregister: user %s (%s) unregistered' % (user.username, jid))
            try:
                user.delete()
            except:
                pass
            return 'Your Jabber account %s was successfully unregistered!' % jid
    cmd_unregister.usage = "PASSWORD"

    def cmd_message(self, mess, *text):
        "Posts the given message to Pownce. The receiver (@public or @friends) is optional."
        if not text:
            return self.cmd_help(mess, "message")
        body = text[:-1]
        receiver = ALLOWED_RECEIVERS.get(text[-1], None)
        if receiver is None:
            body = text
        try:
            user = User.objects.get(jid= mess.getFrom().__str__())
        except User.DoesNotExist:
            return "Please register your Pownce account first."
        else:
            self.log("message: new message from %s: %s" % (user.username, body))
            self.send(mess.getFrom(), "Just a moment please.", mess)
            Note.objects.create(user=user, body=" ".join(body), type="message", to=receiver)
    cmd_message.usage = "NOTE [RECEIVER]"
    cmd_message.alias = ('note', 'msg')
    
    def cmd_link(self, mess, *text):
        "Posts the given link to Pownce. Message and receiver (@public or @friends) are optional."
        text = list(text)
        if len(text) > 1:
            text.pop(1)
        if len(text)==1 and text[0].startswith("@"):
            return self.cmd_help(mess, "link")
        url = text[0]
        if not URL_RE.search(url):
            return "A valid URL is required."
        
        body = text[1:-1]
        receiver = ALLOWED_RECEIVERS.get(text[-1], None)
        if receiver is None:
            body = text[1:]
        try:
            user = User.objects.get(jid=mess.getFrom().__str__())
        except User.DoesNotExist:
            return "Please register your Pownce account first."
        else:
            self.log("link: new link from %s: %s %s" % (user.username, body, url))
            self.send(mess.getFrom(), "Posting link..", mess)
            Note.objects.create(user=user, body=" ".join(body), type="link", link=url, to=receiver)
    cmd_link.usage = "URL [NOTE] [RECEIVER]"
    cmd_link.alias = ('url',)

    def cmd_about(self, mess, *args):
        return "I'm a jabber bot. My creator is jezdez, reachable by email or jabber: jannis@leidel.info"
    cmd_about.alias = ('who', 'wtf', 'howto')

    def cmd_greeting(self, mess, *args):
        return random.choice(GREETINGS).capitalize()+"!"
    cmd_greeting.alias = GREETINGS
    
    def cmd_ping(self, mess, *args):
        return "pong"

def main():
    parser = optparse.OptionParser()
    parser.add_option('-d', '--daemon', dest='daemon', action='store_true',
                help='Tell the Pownce Jabber bot to start as a daemon.')
    options, args = parser.parse_args()
    if len(args):
        parser.error("This program takes no arguments")
    management.call_command('runbot', daemon=options.daemon)

if __name__ == '__main__':
    main()
