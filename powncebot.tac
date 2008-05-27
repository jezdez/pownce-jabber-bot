from twisted.words.protocols.jabber import jid
from twisted.application import service
from wokkel import client, xmppim

from powncebot import settings
from powncebot.bot import PownceBot

username = jid.JID(settings.JABBER_ID)
password = settings.JABBER_PASSWORD

application = service.Application('PownceJabberBot')
client = client.XMPPClient(username, password)
client.logTraffic = True
client.setServiceParent(application)

DEFAULT_STATUS = {'en': "Send stuff! (or 'help' for more information)"}

presence = xmppim.PresenceClientProtocol()
presence.setHandlerParent(client)
presence.available(statuses=DEFAULT_STATUS)

bot = PownceBot(username)
bot.setHandlerParent(client)
