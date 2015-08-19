from __future__ import unicode_literals
from prompt_toolkit.key_binding.manager import KeyBindingManager
from ..api import BangumiSession
from .exception import InvalidCommandError
from .command_executor import CommandExecutorIndex


class AutoCorrector(object):
    key_bindings_manager = KeyBindingManager()
    corrections = {}

    @key_bindings_manager.registry.add_binding(' ')
    @classmethod
    def _(cls, event):
        """
        When space is pressed, we check the word before the cursor, and
        autocorrect that.
        """
        b = event.cli.current_buffer
        w = b.document.get_word_before_cursor()

        if w is not None:
            if w in cls.corrections:
                b.delete_before_cursor(count=len(w))
                b.insert_text(cls.corrections[w])

        b.insert_text(' ')


class CLIBackend(object):
    """Backend for CLI, takes and parses command from CLI, and proxies calls
    to and results from API
    """
    
    _VALID_COMMANDS = CommandExecutorIndex.valid_commands
#     ['kandao', 'kanguo', 'xiangkan', 'paoqi', 'chexiao',
#                        'watched-up-to', 'watched', 'drop', 'want-to-watch',
#                        'remove', 'ls-watching', 'ls-zaikan', 'ls-eps', 'undo']
    
    def __init__(self, email, password):
        self._session = BangumiSession(email, password)
        self._watching = self._session.get_dummy_collections('anime', 3)
        for coll in self._watching:
            AutoCorrector.corrections.update({coll.ch_title, coll.title})
        self._titles = set()
        self._update_titles()
    
    def execute_command(self, command):
        parsed = command.strip().split()
        if not parsed:
            return
        if parsed[0] not in self._VALID_COMMANDS:
            raise InvalidCommandError("Got invalid command: {0}"
                                      .format(parsed[0]))
        executor = (CommandExecutorIndex
                    .get_command_executor(parsed[0])(parsed, self._watching))
        executor.execute()
        self._update_titles()
    
    def get_user_id(self):
        return self._session.user_id
    
    def get_completion_list(self):
        return self._VALID_COMMANDS + list(self._titles)
    
    def get_valid_commands(self):
        return tuple(self._VALID_COMMANDS)
    
    def close(self):
        self._session.logout()
        
    def _parse_command(self, command):
        pass
    
    def _update_titles(self):
        for coll in self._watching:
            sub = coll.subject
            names = ([sub.title, sub.ch_title] +
                     sub.other_info.get('aliases', []))
            for name in names:
                if name not in self._titles:
                    self._titles.add(name)