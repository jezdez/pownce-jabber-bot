import os.path
import urlparse, urllib, urllib2
import cookielib
import xmpp
from datetime import datetime

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.dispatch import dispatcher
from django.db.models import signals
from django.conf import settings
from django.core.mail import mail_admins

from powncebot.signals import post_message_sent, bot_log

LOGIN_ERROR = 'Username and password do not match'
APP_PATH = os.path.dirname(os.path.abspath(__file__))
COOKIEFILE = os.path.join(APP_PATH, 'cookies/%s.txt')
HEADERS =  {'User-agent': 'PownceJabberBot/0.1 (%s)' % urllib.URLopener.version,}
POWNCE_URL = 'https://pownce.com/%s/'
DEFAULT_LINK = 'http://'
DEFAULT_TO = 'public'
ALLOWED_RECEIVERS = {
    '@all': 'all',
    '@friends': 'all',
    '@public': 'public',
}

def pownce_login(username, password):
    """
    Tries to login to pownce.com with the given credentials and return True if
    successful and False if not.
    """
    jar = cookielib.LWPCookieJar()
    cookie = COOKIEFILE % username
    
    if os.path.isfile(cookie):
        jar.load(cookie)
    
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(jar))
    urllib2.install_opener(opener)

    try: # getting the test cookie first
        urllib2.urlopen(urllib2.Request(POWNCE_URL % 'login', None, HEADERS))
    except:
        return False

    # login form preparation
    form = urllib.urlencode({
        'post_data': '',
        'this_is_the_login_form': '1',
        'submit': 'Sign in',
        'username': username,
        'password': password,
    })
    try:
        # login try
        req = urllib2.Request(POWNCE_URL % 'login', form, HEADERS)
        response = urllib2.urlopen(req)
    except IOError, e:
        mail_subject = "Login of user %s was not successful." % username
        mail_body = mail_subject
        if hasattr(e, 'code'):
            mail_body += '\nWe failed with error code - %s.' % e.code
        elif hasattr(e, 'reason'):
            mail_body += "\nThe error object has the following 'reason' attribute :", e.reason
        mail_admins(mail_subject, mail_body, fail_silently=True)
        return False
    else:
        jar.save(cookie)
        return LOGIN_ERROR not in response.read()

def pownce_post(sender, instance, signal, *args, **kwargs):
    """
    Tries to post a given note instance to Pownce when a post_save signal is
    fired.
    """
    note = instance
    username, password = note.credentials()
    
    if pownce_login(username, password) and not note.is_sent:
        form_data = urllib.urlencode({
            'form_name': 'note_form',
            'submit': 'Post It!',
            'note_type': 'note-%s' % note.typ,
            'note_body': note.body,
            'note_to': note.to,
            'url': note.link,
        })
        try:
            req = urllib2.Request(POWNCE_URL % username, form_data, HEADERS)
            response = urllib2.urlopen(req)
        except IOError, e:
            mail_subject = "Posting of %s by user %s was not successful." % (note.typ, username)
            mail_body = mail_subject
            if hasattr(e, 'code'):
                mail_body += '\nWe failed with error code - %s.' % e.code
            elif hasattr(e, 'reason'):
                mail_body += "\nThe error object has the following 'reason' attribute :", e.reason
            mail_admins(mail_subject, mail_body, fail_silently=True)
        else:
            dispatcher.send(signal=bot_log, text="succesfully posted %s by %s." % (note.typ, username))
            dispatcher.send(signal=post_message_sent, user=xmpp.JID(note.user.jid), text="I succesfully posted your %s." % note.typ)
        try:
            note.is_sent = True
            note.save()
        except:
            pass

class User(models.Model):
    username = models.CharField(_('username'), max_length=255)
    password = models.CharField(_('password'), max_length=255, blank=True)
    jid = models.CharField(_('jabber id'), max_length=255, blank=True)
    
    class Admin:
        list_display = ('username', 'jid')
        search_fields = ('username', 'jid')

    class Meta:
        verbose_name = _('user')

    def __unicode__(self):
        return self.username
    
class Note(models.Model):
    user = models.ForeignKey(User, verbose_name=_("user"))
    body = models.TextField(_('note body'), blank=True)
    typ = models.CharField(_("type"), max_length=100)
    link = models.CharField(_("link"), max_length=100, default=DEFAULT_LINK)
    to = models.CharField(_("to"), max_length=100, default=DEFAULT_TO, blank=True)
    created = models.DateTimeField(_("created"), default=datetime.now)
    is_sent = models.NullBooleanField(_("is sent"), blank=True, null=True)
    
    class Admin:
        list_display = ('user', 'created', 'typ', 'is_sent')
        list_filter = ('is_sent', 'typ', 'to')

    class Meta:
        verbose_name = _('note')

    def __unicode__(self):
        return self.body[0:10]
    
    def credentials(self):
        return (self.user.username, self.user.password)

dispatcher.connect(pownce_post, sender=Note, signal=signals.post_save)
