import inspect

from twisted.python import log
from twisted.words.xish import domish
from twisted.words.xish.domish import Element as DomishElement

from wokkel.xmppim import MessageProtocol

from powncebot import commands, accounts

HELP_COMMANDS = ('register', 'unregister', 'link', 'message', 'help', 'about')

class PownceBot(MessageProtocol):
    """This is a Pownce jabber bot."""
    def __init__(self, jid):
        MessageProtocol.__init__(self)
        self.jid = jid
        self.help = []

        self.commands = {}
        for (name, klass) in inspect.getmembers(commands, inspect.isclass):
            if not name in ('Command', 'User'):
                self.commands[name] = klass
                if hasattr(klass, 'aliases'):
                    for alias in klass.aliases:
                        self.commands[alias] = klass
                if name in HELP_COMMANDS:
                    if hasattr(klass, 'usage'):
                        self.help.append("%s %s" % (name, klass.usage))
        self.help = "\n".join(self.help)
        self.session = accounts.Datastore().get_session()

    def getCommand(self, command):
        return self.commands.get(command, commands.unknown)

    def reply(self, jid, content):
        message = domish.Element((None, "message"))
        message['to'] = jid
        message['from'] = self.jid.full()
        message['type'] = 'chat'
        message.addUniqueId()
        message.addElement((None,'body'), content=content)
        self.xmlstream.send(message)

    def onMessage(self, message):
        """Messages sent to the bot will arrive here. Command handling routing
        is done in this function."""
        if not isinstance(message.body, DomishElement):
            return None

        text = unicode(message.body).encode('utf-8').strip()
        cmdargs = text.split()
        command = cmdargs[0].lower()
        args = cmdargs[1:]
        if command.endswith(':'):
            command = command[:-1]
        self.getCommand(command)(self, message, *args)
