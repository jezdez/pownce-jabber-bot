from twisted.words.protocols.jabber.jid import JID
from twisted.application import service
from wokkel import client, xmppim

from powncebot import settings, PownceBot

DEFAULT_STATUS = {None: "Send stuff! (or 'help' for more information)"}

class BotPresenceClientProtocol(xmppim.PresenceClientProtocol):
    """
    A custom presence protocol to automatically accept any subscription
    attempt.
    """
    def subscribeReceived(self, entity):
        self.subscribed(entity)
        self.available(statuses=DEFAULT_STATUS)

    def unsubscribeReceived(self, entity):
        self.unsubscribed(entity)


jid = JID(settings.JABBER_ID)
application = service.Application('powncebot')

client = client.XMPPClient(jid, settings.JABBER_PASSWORD)
client.logTraffic = True
client.setServiceParent(application)

presence = BotPresenceClientProtocol()
presence.setHandlerParent(client)
presence.available(statuses=DEFAULT_STATUS)

roster = xmppim.RosterClientProtocol()
roster.setHandlerParent(client)

bot = PownceBot(jid)
bot.setHandlerParent(client)
