"""
MIT License

Copyright (c) 2019 WaferJay

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import re

from ..common import get_content, urls_size, log
from ..extractor import VideoExtractor


class NoMatchException(Exception):
    pass


class _Dispatcher(object):

    def __init__(self):
        self.entry = []

    def register(self, patterns, fun):
        if not isinstance(patterns, (list, tuple)):
            patterns = [patterns]

        patterns = [re.compile(reg) for reg in patterns]
        self.entry.append((patterns, fun))

    def endpoint(self, *patterns):
        def _wrap(fun):
            self.register(patterns, fun)
            return fun
        return _wrap

    def dispatch(self, url, *args, **kwargs):

        for patterns, fun in self.entry:

            for pa in patterns:

                match = pa.search(url)
                if not match:
                    continue

                kwargs.update(match.groupdict())
                return fun(*args, **kwargs)

        raise NoMatchException()


missevan_stream_types = [
    {'id': '128bit', 'url_json_key': 'soundurl_32'},
    {'id': '64bit', 'url_json_key': 'soundurl_64'},
    {'id': '32bit', 'url_json_key': 'soundurl_128'}
]


class MissEvanWithStream(VideoExtractor):

    name = 'MissEvan'
    stream_types = missevan_stream_types

    @classmethod
    def create(cls, title, streams, streams_sorted=None):
        obj = cls()
        obj.title = title
        obj.streams.update(streams)
        streams_sorted = streams_sorted or cls._setup_streams_sorted(streams)
        obj.streams_sorted.extend(streams_sorted)
        return obj

    @staticmethod
    def _setup_streams_sorted(streams):
        streams_sorted = []
        for key, stream in streams.items():
            copy_stream = stream.copy()
            copy_stream['id'] = key
            streams_sorted.append(copy_stream)

        return streams_sorted

    def download(self, **kwargs):
        stream_id = kwargs.get('stream_id') or self.stream_types[0]['id']
        stream = self.streams[stream_id]
        if 'size' not in stream:
            stream['size'] = urls_size(stream['src'])

        super().download(**kwargs)

    def unsupported_method(self, *args, **kwargs):
        raise AssertionError('Unsupported')

    download_by_url = unsupported_method
    download_by_vid = unsupported_method
    prepare = unsupported_method
    extract = unsupported_method


class MissEvan(VideoExtractor):

    name = 'MissEvan'
    stream_types = missevan_stream_types

    _SOUND_URL_PREFIX = 'https://static.missevan.com/'

    _P_ALBUM_URL = re.compile(r'missevan\.com/album(?:info)?/(?P<aid>\d+)', re.I)

    @classmethod
    def is_album_url(cls, url):
        return bool(cls._P_ALBUM_URL.search(url))

    @classmethod
    def parse_album_id(cls, url):
        match = cls._P_ALBUM_URL.search(url)
        if not match:
            raise ValueError()
        return match.group('aid')

    def download_by_url(self, url, **kwargs):
        if not kwargs.get('playlist') and self.is_album_url(url):
            log.w('This is an album. (use --playlist to download all audios).')
        else:
            super().download_by_url(url, **kwargs)

    __prepare_dispatcher = _Dispatcher()

    @__prepare_dispatcher.endpoint(
        re.compile(r'missevan\.com/sound/(?:player\?.*?id=)?(?P<sid>\d+)', re.I))
    def prepare_sound(self, sid, **kwargs):
        content = get_content('https://www.missevan.com/sound/getsound?soundid=' + sid)
        json_data = json.loads(content)
        sound = json_data['info']['sound']

        q32_url = self._SOUND_URL_PREFIX + sound['soundurl_32']
        q64_url = self._SOUND_URL_PREFIX + sound['soundurl_64']
        q128_url = self._SOUND_URL_PREFIX + sound['soundurl_128']

        self.streams = {
            '32bit': {
                'src': [q32_url],
                'container': 'mp3'
            },
            '64bit': {
                'src': [q64_url],
                'container': 'mp3'
            },
            '128bit': {
                'src': [q128_url],
                'container': 'mp3'
            }
        }
        self.title = sound['soundstr']

    def prepare(self, **kwargs):
        if self.vid:
            self.prepare_sound(self.vid, **kwargs)
            return

        try:
            self.__prepare_dispatcher.dispatch(self.url, self, **kwargs)
        except NoMatchException:
            log.e('[Error] Unsupported URL pattern.')
            exit(1)

    def download_playlist_by_url(self, url, **kwargs):
        self.url = url
        aid = None
        try:
            aid = self.parse_album_id(url)
        except ValueError:
            log.e('[Error] Unsupported URL pattern with --playlist option.')
            exit(1)

        # use the best quality by default
        kwargs.setdefault('stream_id', missevan_stream_types[0]['id'])

        content = get_content('https://www.missevan.com/sound/soundalllist?albumid=' + aid)
        json_data = json.loads(content)
        album = json_data['info']['album']
        self.title = album['title']
        sounds = json_data['info']['sounds']

        for sound in sounds:
            streams = {}

            for stream_type in missevan_stream_types:
                sound_url = self._SOUND_URL_PREFIX + sound[stream_type['url_json_key']]
                streams[stream_type['id']] = {'src': [sound_url], 'container': 'mp3'}

            sound_title = sound['soundstr']
            MissEvanWithStream \
                .create(sound_title, streams) \
                .download(**kwargs)

    def extract(self, **kwargs):
        stream_id = kwargs.get('stream_id') or missevan_stream_types[0]['id']
        stream = self.streams[stream_id]
        if 'size' not in stream:
            stream['size'] = urls_size(stream['src'])

site = MissEvan()
site_info = 'MissEvan.com'
download = site.download_by_url
download_playlist = site.download_playlist_by_url
