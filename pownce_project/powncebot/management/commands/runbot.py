from django.core.management.base import NoArgsCommand
from django.utils.daemonize import become_daemon
from django.dispatch import dispatcher
from django.conf import settings
from optparse import make_option

from powncebot.bot import PownceJabberBot
from powncebot.signals import post_message_sent, bot_log

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option('--daemon', '-d', action='store_true', dest='daemon',
            help='Tell the Pownce Jabber bot to start as a daemon.'),
    )
    help = 'Used to start the Pownce Jabber bot.'
    
    def handle_noargs(self, **options):
        use_daemon = options.get('daemon', False)
        
        # become a true daemon
        if use_daemon:
            become_daemon()
        # initializing bot
        powncebot = PownceJabberBot(settings.JABBER_ID,
                                    settings.JABBER_PASSWORD,
                                    settings.JABBER_RESOURCE,
                                    use_daemon)
        # connect signals to senders
        dispatcher.connect(powncebot.send, signal=post_message_sent)
        dispatcher.connect(powncebot.log, signal=bot_log)
        # serve as long it's restarted or quitted
        powncebot.serve_forever()
