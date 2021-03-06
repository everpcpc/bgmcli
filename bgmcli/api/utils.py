# -*- coding: utf-8 -*-
"""Utility functions for the package
"""

import re
from bs4 import BeautifulSoup


def to_unicode(s):
    """Converts a str to unicode
    
    Args:
        s (any): the object to process
        
    Returns:
        unicode if input is str, otherwise just the input value
    """
    if isinstance(s, str):
        result = s.decode('utf-8')
    else:
        result = s
    return result


def get_encoding_from_html(html):
    """Get encoding info from html
    
    Args:
        html (unicode or str): any html
    
    Returns:
        str: encoding for the html page, empty string if not available
    """
    try:
        return re.search('<meta charset="(.+)"', html).group(1)
    except:
        return ""


def get_checked_values(soup):
    """Get the values for checked input tags
    
    Args:
        soup (BeautifulSoup): parsed html of a form in any page
        
    Returns:
        list[unicode]: values that are checked in the form 
    """
    return [i['value'] for i in soup.find_all('input')
            if i.has_attr('checked')]


def get_user_id_from_html(html):
    """Get user_id from html of home or subject or episode page when logged in
    
    Args:
        html (unicode or str): html of home, subject, or episode page
        
    Returns:
        str or unicode: user id of the logged in user
    """
    soup = BeautifulSoup(html, 'html.parser')
    return get_user_id_from_soup(soup)


def get_user_id_from_soup(soup):
    """Get user_id from parsed html of home or subject or episode page when
    logged in
    
    Args:
        soup (BeautifulSoup): parsed html of home, subject, or episode page
        
    Returns:
        str or unicode: user id of the logged in user
    """
    user_id = (soup
               .find(class_='idBadgerNeue')
               .find(class_='avatar')['href']
               .split('/')[-1])
    return user_id


def get_ep_ids_up_to_this(episode):
    """Get list of episode ids in the same subject prior to this one,
    inclusive
    
    Args:
        episode (BangumiEpisode): the episode to search up to
        
    Returns:
        list[str]: list of episode ids
    """
    subject = episode.subject
    eps = subject.eps
    ep_ids = []
    for ep in eps:
        ep_ids.append(ep.id_)
        if ep.id_ == episode.id_:
            break
    return ep_ids


def get_ep_colls_up_to_this(ep_coll):
    """Get list of episode collections in the same subject prior to this one,
    inclusive
    
    Args:
        ep_coll (BangumiEpisodeCollection): the episode to search up to
        
    Returns:
        list[BangumiEpisodeCollection]: list of episode collections
    """
    sub_coll = ep_coll.sub_collection
    ep_colls = []
    for ep_c in sub_coll.ep_collections:
        ep_colls.append(ep_c)
        if ep_c == ep_coll:
            break
    return ep_colls


def check_response(response):
    """check if response indicates successful request.
    
    It's considered successful if status code is 200 and the html in response
    still indicates that user is logged in.
    
    Args:
        response (requests.models.Response): response from a http request
        
    Returns:
        bool: True if successful
    """
    if response.status_code != 200:
        return False
    try:
        get_user_id_from_html(response.text)
    except TypeError:
        return False
    else:
        return True
    
    
def get_subject_type_from_soup(soup):
    """Get the type of subject from the page provided"""
    return soup.find(id='navMenuNeue').find(class_='focus')['href'][1:]


def get_n_watched_eps_from_soup(soup):
    """Get number of watched episodes"""
    return int(soup.find(id='watchedeps')['value'])

def get_n_pages(html):
    """Get number of pages for a multipage collection list"""
    soup = BeautifulSoup(html, 'html.parser')
    pages = soup.find(id='multipage').find_all(class_='p')
    if not pages:
        return 1
    cur_page = int(soup.find(id='multipage').find(class_='p_cur').text)
    avail_pages = [int(p['href'].rsplit('=')[-1]) for p in pages]
    return max(avail_pages + [cur_page])
        
    
        