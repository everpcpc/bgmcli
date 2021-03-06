# -*- coding: utf-8 -*-
"""Library that defines a login session for Bangumi
"""

import re
from functools import wraps
import requests
from bs4 import BeautifulSoup
from .exception import LoginFailedError, NotLoggedInError, RequestFailedError
from .element import BangumiEpisode, BangumiSubjectFactory
from .collection import BangumiEpisodeCollection, BangumiSubjectCollection,\
    BangumiSubjectCollectionFactory, BangumiDummySubjectCollection
from .utils import get_ep_colls_up_to_this, check_response, to_unicode,\
    get_user_id_from_html, get_encoding_from_html, get_n_pages,\
    get_n_watched_eps_from_soup


def require_login(method):
    """Decorator function that raises NotLoggedInError if not logged in"""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self._logged_in:
            raise NotLoggedInError("Please login first!")
        else:
            return method(self, *args, **kwargs)
    return wrapper


class BangumiSession(object):
    """This class abtracts a login session for Bangumi and provides methods
    to retrieve and set element/collection data
    
    Note:
        The subject methods currently only work for anime subjects and subject
        collection methods only work for anime collections
    """

    _VALID_DOMAIN = ('bgm.tv', 'bangumi.tv', 'chii.in')

    def __init__(self, email, password, domain='bgm.tv'):
        """Constructs a `BangumiSession`

        Args:
            email (str): the login _email address
            password (str): the password for login
            domain (str): the domain to use for login must be one of
                          ['bgm.tv', 'bangumi.tv', 'chii.in']
            
        Raises:
            LoginFailedError: If login failed
            ValueError: if domain is not valid
        """
        if domain not in self._VALID_DOMAIN:
            raise ValueError("Domain must be one of {0}"
                             .format(self._VALID_DOMAIN))
        self._session = requests.Session()
        self._base_url = (domain if domain.startswith('http://')
                          else 'http://' + domain)
        self._email = email
        self._logged_in = False
        self._login(email, password)
        self._gh = self._get_gh()
        self._user_id = self._get_user_id()
        
    def __enter__(self):
        return self
    
    def __exit__(self, type_, value, traceback):
        self.logout()

    def get_subject(self, sub_id):
        """Get crucial data for specified subject
        Args:
            sub_id (str): subject id

        Returns:
            BangumiAnime: object containing data for specified subject
        """
        sub_html = self._get_html_for_subject_main(sub_id)
        ep_html = self._get_html_for_subject_eps(sub_id)
        return BangumiSubjectFactory.from_html(sub_html, ep_html)

    def get_episode(self, ep_id):
        """Get crucial data for specified episode
        Args:
            ep_id (str): episode id

        Returns:
            BangumiEpisode: object containing data for specified episode
        """
        sub_id = self._get_sub_id_for_ep(ep_id)
        html = self._get_html_for_subject_eps(sub_id)
        return BangumiEpisode.from_html(ep_id, html)

    def get_episodes_for_sub(self, sub_id):
        """Get crucial data for all episodes under specified subject
        Args:
            sub_id (str): subject id

        Returns:
            list of BangumiEpisode: list of objects containing data for
                specified episode
        """
        html = self._get_html_for_subject_eps(sub_id)
        return BangumiEpisode.eps_from_html(html)

    def get_sub_collection(self, sub_id):
        """Get data and collection info for specified subject
        Args:
            sub_id (str): subject id

        Returns:
            BangumiSubjectCollection: containing data and collection info for
                subject. Empty collection with only subject if it's not in
                user's collection
        """
        sub_html = self._get_html_for_subject_main(sub_id)
        ep_html = self._get_html_for_subject_eps(sub_id)
        sub_coll = BangumiSubjectCollectionFactory.from_html(sub_html,
                                                             ep_html)
        sub_coll.session = self
        return sub_coll

    def get_sub_collection_with_subject(self, subject):
        """"Get data collection info for specified subject with provided
        `BangumiAnime` object.

        Args:
            subject (BangumiAnime): subject for which to get collection info

        Returns:
            BangumiSubjectCollection: containing data and collection info for
                subject. Empty collection with only subject if it's not in
                user's collection
        """
        sub_html = self._get_html_for_subject_main(subject.id_)
        ep_html = self._get_html_for_subject_eps(subject.id_)
        sub_collection = (BangumiSubjectCollectionFactory
                          .from_html_with_subject(subject, sub_html, ep_html))
        sub_collection.session = self
        return sub_collection

    def get_ep_collection(self, ep_id):
        """Get data and collection info for specified episode
        Args:
            ep_id (str): episode id

        Returns:
            BangumiEpisodeCollection: containing data and collection info for
                episode. Empty collection with only episode if it's not in
                user's collection
        """
        sub_id = self._get_sub_id_for_ep(ep_id)
        html = self._get_html_for_subject_eps(sub_id)
        ep_coll = BangumiEpisodeCollection.from_html(ep_id, html)
        ep_coll.session = self
        return ep_coll

    def get_ep_collection_with_episode(self, episode):
        """Get collection info for given episode
        Args:
            episode (BangumiEpisode): episode for which to get collection info

        Returns:
             BangumiEpisodeCollection: containing data and collection info for
                episode. Empty collection with only episode if it's not in
                user's collection
        """
        sub_id = self._get_sub_id_for_ep(episode.id_)
        html = self._get_html_for_subject_eps(sub_id)
        ep_collection = BangumiEpisodeCollection.from_html_with_ep(episode,
                                                                   html)
        ep_collection.session = self
        return ep_collection
    
    def set_collection(self, collection):
        """Update the collection info on Bangumi according to provided
        collection object
        
        Note:
            In the case of BangumiAnimeCollection, episode collections
            contained will not be set. Need to explicitly call
            set_ep_collection or set_n_watched_eps to set status for
            episode collections.
            
        Args:
            collection (BangumiCollection): the object containing data to
                update to Bangumi

        Returns:
            bool: True if successful. False otherwise.
            
        Raises: 
            TypeError: if argument is neither BangumiSubjectCollection or
                BangumiEpisodeCollection
            NotLoggedInError: if not logged in
        """
        if isinstance(collection, BangumiSubjectCollection):
            return self.set_sub_collection(collection)
        elif isinstance(collection, BangumiEpisodeCollection):
            return self.set_ep_collection(collection)
        else:
            raise TypeError("Must be either BangumiSubjectCollection or " + 
                            "BangumiEpisodeCollection, got {0}"
                            .format(type(collection)))

    def set_sub_collection(self, sub_coll):
        """Update the collection info on Bangumi according to provided
        BangumiSubjectCollection object

        Note:
            episode collections contained will not be set. Need to explicitly
            call set_ep_collection() or set_n_watched_eps() to set status for
            episode collections.

        Args:
            sub_coll (BangumiSubjectCollection): the object containing data
                to update to Bangumi

        Returns:
            bool: True if successful.
            
        Raises:
            TypeError: if argument not BangumiSubjectCollection
            AttributeError: if c_status is not set
            ValueError: if c_status not valid
            NotLoggedInError: if not logged in
        """
        if not isinstance(sub_coll, BangumiSubjectCollection):
            raise TypeError('Collection must be a BangumiSubjectCollection!' +
                            'Got {0}'.format(type(sub_coll)))
        if not sub_coll.c_status:
            raise AttributeError("c_status not set. Use remove methods to " +
                                 "remove a collection")
        if sub_coll.c_status not in BangumiSubjectCollection._VALID_C_STATUS:
            raise ValueError('Corrupted c_status value: ' +
                             str(sub_coll.c_status))

        data = {'referer': 'subject', 'interest': sub_coll._c_status,
                'rating': str(sub_coll.rating) if sub_coll.rating else '',
                'tags': u' '.join(sub_coll.tags),
                'comment': sub_coll.comment, 'update': u'保存'}
        set_coll_url = '{0}/subject/{1}/interest/update?gh={2}'.format(
            self._base_url, sub_coll.subject.id_, self._gh)
        response = self._post(set_coll_url, data)

        return check_response(response)

    def set_ep_collection(self, ep_coll):
        """Update the collection info on Bangumi according to provided
        BangumiEpisodeCollection object

        Args:
            ep_coll (BangumiEpisodeCollection): the object containing data
                to update to Bangumi

        Returns:
            bool: True if successful.
            
        Raises:
            TypeError: if argument not BangumiEpisodeCollection
            AttributeError: if c_status is not set
            ValueError: if c_status not valid
            NotLoggedInError: if not logged in
        """
        if not isinstance(ep_coll, BangumiEpisodeCollection):
            raise TypeError('Must be a BangumiEpisodeCollection! Got {0}'
                            .format(type(ep_coll)))
        if not ep_coll.c_status:
            raise AttributeError("c_status not set. Use remove methods to " +
                                 "remove a collection")
        if ep_coll.c_status not in BangumiEpisodeCollection._VALID_C_STATUS:
            raise ValueError('Corrupted c_status value: {0}'
                             .format(ep_coll.c_status))
        if ep_coll.c_status == 'watched_up_to':
            if ep_coll.sub_collection is None:
                raise AttributeError("Containing subject collection not " +
                                     "defined for c_status 'watched_up_to'")
            else:
                ep_colls = get_ep_colls_up_to_this(ep_coll)
                return self._set_watched_eps_in_sub(ep_colls)
        else:
            set_url = ('{0}/subject/ep/{1}/status/{2}?gh={3}'
                       .format(self._base_url, ep_coll.episode.id_,
                               ep_coll.c_status, self._gh))
            response = self._get(set_url)
            # update n_watched_eps in subject collection
            if ep_coll.sub_collection:
                soup = BeautifulSoup(response.text, 'html.parser')
                n_watched_eps = get_n_watched_eps_from_soup(soup)
                ep_coll.sub_collection.n_watched_eps = n_watched_eps
        return check_response(response)

    def remove_collection(self, collection):
        """Remove the collection on Bangumi and clear c_status locally
        
        Returns:
            bool: True if successful
        """
        if isinstance(collection, BangumiSubjectCollection):
            result = self._remove_sub_collection(collection.subject.id_)
        elif isinstance(collection, BangumiEpisodeCollection):
            result = self._remove_ep_collection(collection.episode.id_)
        else:
            raise TypeError("Collection type invalid!")
        collection._c_status = None
        return result
        
    def set_n_watched_eps(self, sub_collection):
        """Update number of watched episodes to Bangumi according to provided
        sub_collection
        
        Note: the behavior may be weird sometimes but it's defined on Bangumi
        
        Args:
            sub_collection (BangumiAnimeCollection): a subject collection
                with c_status > 1 and defined n_watched_eps
                
        Returns:
            bool: True if successful
        """
        if sub_collection.c_status == 1:
            raise ValueError("c_status must not be 1")
        if sub_collection.n_watched_eps is None:
            raise AttributeError("n_watched_eps must be defined")
        result = self._set_n_watched_eps(sub_collection.subject.id_,
                                         sub_collection.n_watched_eps)
        if result:
            sub = sub_collection.subject
            html = self._get_html_for_subject_eps(sub.id_)          
            sub_collection.ep_collections = (BangumiEpisodeCollection
                                             .ep_colls_for_sub_from_html(sub,
                                                                         html))
            for ep_coll in sub_collection.ep_collections:
                ep_coll.session = sub_collection.session
                ep_coll.sub_collection = sub_collection
            return True
        else:
            return False
        
    def get_dummy_collections(self, sub_type, c_status, user_id=None):
        """Get a list of dummy collections with basic information for
        subjects in specified c_status and with specified sub_type
        
        Args:
            sub_type (str): must be among 'anime', 'book', 'game', 'real'
            c_status (int): as in c_status of BangumiSubjectCollection, must
                be int >= 1 and <= 5
            user_id (str): user id to get list for
        
        Returns:
            list[tuple(str)]: list of subject basic information as specified
        """
        if sub_type not in ('anime', 'book', 'game', 'real'):
            raise ValueError("Invalid subject type provided: {0}"
                             .format(sub_type))
        if c_status not in range(1, 6):
            raise ValueError("Invalid c_status provided: {0}"
                             .format(c_status))
        if not user_id:
            user_id = self._user_id
        c_status_map = {1: 'wish', 2: 'collect', 3: 'do', 4: 'on_hold',
                        5: 'dropped'}
        text_c_status = c_status_map[c_status]
        url = '{0}/{1}/list/{2}/{3}'.format(self._base_url, sub_type, user_id,
                                            text_c_status)
        response = self._get(url)
        n_pages = get_n_pages(response.text)
        dummy_colls = []
        for p in xrange(1, n_pages + 1):
            dummy_colls += self._get_dummy_colls_on_page(url, p, c_status)
        for coll in dummy_colls:
            coll.session = self
        return dummy_colls

    @require_login
    def logout(self):
        """Logout the session"""
        self._logged_in = False
        self._session.get('{0}/logout/{1}'.format(self._base_url, self._gh))
        self._session.close()
        
    @property
    def user_id(self):
        """str: user id
        """
        return self._user_id
    
    @property
    def email(self):
        """str: email address used for login
        """
        return self._email
        
    def _set_watched_eps_in_sub(self, ep_colls):
        """Set all episodes in ep_colls to watched both locally and to Bangumi

        Note:
            All entries in ep_colls must belong to the same subject collection
            
        Returns:
            bool: True if successful
        """
        sub_coll = ep_colls[0].sub_collection
        for ep_coll in ep_colls:
            if ep_coll.sub_collection is not sub_coll:
                raise ValueError("Exists entry in ep_coll not belong to " +
                                 "same subject collection!")
        ep_ids = [ep_c.episode.id_ for ep_c in ep_colls]
        base_ep_id = ep_ids[-1]
        ep_ids_str = ','.join(ep_ids)
        data = {'ep_id': ep_ids_str}
        set_url = ('{0}/subject/ep/{1}/status/watched?gh={2}&ajax=1'
                   .format(self._base_url, base_ep_id, self._gh))
        response = self._post(set_url, data)
        if (response.status_code == 200 and
            response.text == u'{"status":"ok"}'):
            # update n_watched_eps as well as ep_collections
            html = self._get_html_for_subject_main(sub_coll.subject.id_)
            soup = BeautifulSoup(html, 'html.parser')           
            sub_coll.n_watched_eps = get_n_watched_eps_from_soup(soup)
            for ep_c in ep_colls:
                ep_c.c_status = 'watched'
            return True
        else:
            return False

    def _remove_sub_collection(self, sub_id):
        rm_url = '{0}/subject/{1}/remove?gh={2}'.format(self._base_url,
                                                         sub_id, self._gh)
        response = self._get(rm_url)
        return check_response(response)

    def _remove_ep_collection(self, ep_id):
        rm_url = ('{0}/subject/ep/{1}/status/remove?gh={2}'
                  .format(self._base_url, ep_id, self._gh))
        response = self._get(rm_url)
        return check_response(response)

    def _set_n_watched_eps(self, sub_id, n_watched_eps):
        set_url = '{0}/subject/set/watched/{1}'.format(self._base_url, sub_id)
        data = {'referer': 'subject', 'submit': u'更新',
                'watchedeps': str(n_watched_eps)}
        response = self._post(set_url, data)
        return check_response(response)

    def _get_user_id(self):
        response = self._get(self._base_url)
        return get_user_id_from_html(response.text)

    def _get_html_for_ep(self, ep_id):
        ep_url = '{0}/ep/{1}'.format(self._base_url, ep_id)
        response = self._get(ep_url)
        response.encoding = get_encoding_from_html(response.text)
        return response.text

    def _get_sub_id_for_ep(self, ep_id):
        html = self._get_html_for_ep(ep_id)
        soup = BeautifulSoup(html, 'html.parser')
        sub_id = soup.find(id='subject_inner_info').a['href'].split('/')[-1]
        return sub_id

    def _get_html_for_subject_main(self, sub_id):
        sub_url = '{0}/subject/{1}'.format(self._base_url, sub_id)
        response = self._get(sub_url)
        response.encoding = get_encoding_from_html(response.text)
        return response.text

    def _get_html_for_subject_eps(self, sub_id):
        sub_url = '{0}/subject/{1}/ep'.format(self._base_url, sub_id)
        response = self._get(sub_url)
        response.encoding = get_encoding_from_html(response.text)
        return response.text
    
    def _get_dummy_colls_on_page(self, url, page, c_status):
        page_url = '{0}?page={1}'.format(url, page)
        response = self._get(page_url)
        if response.status_code != 200:
            raise RequestFailedError("Request Failed")
        response.encoding = get_encoding_from_html(response.text)
        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.find(id='browserItemList').find_all('li')
        return [BangumiDummySubjectCollection.from_soup_for_li(i, c_status)
                for i in items]


    def _login(self, email, password):
        data = {'email': email, 'password': password,
                'loginsubmit': to_unicode('登录')}
        response = self._session.post(self._base_url + '/FollowTheRabbit',
                                      data)
        response.encoding = get_encoding_from_html(response.text)
        if to_unicode('欢迎您回来。现在将转入登录前页面') in response.text:
            self._logged_in = True
        else:
            print response.text
            raise LoginFailedError("Login failed.")

    def _get_gh(self):
        response = self._get(self._base_url)
        match_result = re.search(
            '<a href="{0}/logout/(.*?)">'.format(self._base_url),
            response.text)
        return match_result.group(1)
    
    @require_login
    def _get(self, url):
        return self._session.get(url)
    
    @require_login
    def _post(self, url, data):
        return self._session.post(url, data)
