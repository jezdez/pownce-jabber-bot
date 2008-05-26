import pownce
import simplejson
from urllib import urlencode
from urllib2 import HTTPError

from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker, mapper

from powncebot import settings

class Api(pownce.Api):
    def send_to_default(self):
        """
        Gets the list of potential recipients for the authenticated user.
        """
        query_dict = {'app_key' : self.app_key}
        url = '%ssend/send_to.json?%s' % (self.API_URL, urlencode(query_dict))
        json_obj = simplejson.loads(self._fetch(url))
        if 'selected' in json_obj.keys():
            return json_obj['selected']
        elif 'error' in json_obj.keys():
            error_class = self.ERROR_MAPPING[json_obj['error']]
            raise error_class("Error retrieving 'send_to' list: %s" % error['message'])

class Datastore(object):
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URI,
                    echo=getattr(settings, "DATABASE_ECHO", False))
        self.metadata = MetaData(bind=self.engine)
        users_table = Table("users", self.metadata,
            Column("id", Integer, primary_key=True),
            Column("username", String(64)),
            Column('password', String(32)),
            Column('jid', String(255)),
        )
        mapper(User, users_table)
        self.metadata.create_all()
        self.session = sessionmaker(bind=self.engine)()
    
    def get_session(self):
        return self.session

class User(object):
    def __init__(self, username, password, jid):
        self.username = username
        self.password = password
        self.jid = jid

    def __repr__(self):
        return "<User('%s, '%s')>" % (self.username, self.jid)

def login(username, password):
    """
    Tries to login to pownce.com with the given credentials and return
    an api and a user object if successful.
    """
    api = Api(username, password, settings.APPLICATION_KEY)
    try:
        user = api.get_user(username)
    except HTTPError:
        raise pownce.AuthenticationRequired
    else:
        return api
