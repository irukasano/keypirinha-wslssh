
import keypirinha as kp
import keypirinha_util as kpu

from collections import namedtuple, OrderedDict
import winreg
import re
import sys
import traceback

# type ssh + tab
# catalog item is made from .ssh/config of wsl
class WslSsh(kp.Plugin):
    CONFIG_SECTION_MAIN = "main"
    CONFIG_SECTION_PROFILE = "profile/"

    DEFAULT_CONFIG_DEBUG = False
    DEFAULT_CONFIG_COMMAND_LINE = "c:\\Program Files\\ConEmu\\ConEmu64.exe -run %s -c 'ssh %s'"
    DEFAULT_CONFIG_ARGS = "-run {} -c 'ssh {}'"
    DEFAULT_CONFIG_BASH_USER = "admin"

    ssh_configs = []
    config_debug = DEFAULT_CONFIG_DEBUG
    config_command_line = DEFAULT_CONFIG_COMMAND_LINE
    config_args = DEFAULT_CONFIG_ARGS
    config_bash_user = DEFAULT_CONFIG_BASH_USER
    profiles = OrderedDict()

    def __init__(self):
        super().__init__()
        self.ssh_configs = []

    def on_start(self):
        self.get_config()
        self.get_ssh_config()

    def on_catalog(self):
        self.set_catalog([
            self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label="SSH",
                short_desc="SSH to servers defined .ssh/config on Windows Subsystem for Linux ",
                target="ssh",
                args_hint=kp.ItemArgsHint.REQUIRED,
                hit_hint=kp.ItemHitHint.KEEPALL
            )
        ])

    def on_suggest(self, user_input, items_chain):
        if not items_chain or items_chain[0].category() != kp.ItemCategory.KEYWORD:
            return

        if self.should_terminate(0.250):
            return

        mylist = self.filterbyvalue(self.ssh_configs, user_input)
        if (len(mylist)):
            self.set_suggestions(mylist, kp.Match.ANY, kp.Sort.LABEL_ASC)
    
    def filterbyvalue(self, seq, value):
        return list(filter(lambda item: value.lower() in item.label().lower(), seq))

    def on_execute(self, item, action):
        # execute conemu and ssh command
        # c:\Program Files\ConEmu>ConEmu64.exe -run {Bash::bash} -c 'ssh some-server-name-defined-in-ssh-config'
        data_bag = item.data_bag().split('|')
        server_name = data_bag[0]
        conemu_task = data_bag[1]

        # ssh in the conemu
        if ((action and action.name() == 'ssh') or not action):
            cmd = self.config_command_line
            args = self.config_args.format(
                conemu_task,
                server_name
            )
            
            if ( self.config_debug):
                self.log(cmd)
                self.log(args)
            
            kpu.shell_execute(cmd, args)
            return

    def create_actions(self):
        general_actions = [
            self.create_action(name="ssh", label="ssh with conemu", short_desc="ssh with conemu")
        ]

        self.set_actions(FunctionSuggestion.ITEMCAT, general_actions)
        self.set_actions(ClassSuggestion.ITEMCAT, general_actions)

    def on_events(self, flags):
        if flags & kp.Events.PACKCONFIG:
            self.get_config()

    def get_ssh_config(self):
        basePath = self.get_wsl_basepath()
        if ( basePath != False):
            self.read_ssh_config(basePath)
            self.log(self.ssh_configs)

    def get_wsl_basepath(self):
        try:
            # get default wsl from registory
            # HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss
            path = 'Software\\Microsoft\\Windows\\CurrentVersion\\Lxss'
            self.log(path)
            key = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, path, access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
            defaultDistribution, regtype = winreg.QueryValueEx(key, 'DefaultDistribution')
            winreg.CloseKey(key) 

            path = path + '\\' + defaultDistribution
            self.log(path)
            key = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, path, access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
            basePath, regtyp = winreg.QueryValueEx(key, 'BasePath')
            winreg.CloseKey(key)
        except:
            basePath = False
            traceback.print_exc()
        
        return basePath

    def read_ssh_config(self, basePath):
        ssh_config = basePath + "\\rootfs\\home\\%s\\.ssh\\config" % self.config_bash_user
        p = re.compile('^H[oO][sS][tT][ \t](.+)$')

        # find "^HOST "
        try:
            with open(ssh_config, 'r', encoding="latin1") as f:
                for line in f.readlines():
                    r = p.match(line)
                    if r:
                        label = r.group(1)
                        short_desc = "ssh %s" % label
                        task = self.get_task_by_server_name(label)
                        suggestion = self.create_item(
                            category=kp.ItemCategory.KEYWORD,
                            label=label,
                            short_desc=short_desc,
                            target=label,
                            data_bag="{}|{}".format(label,task),
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.IGNORE
                        )
                        self.ssh_configs.append(suggestion)
        except:
            traceback.print_exc()

    def get_task_by_server_name(self, server_name):
        result = self.profiles['default']['task_name']
        if ( self.config_debug):
            self.log(server_name)
        for profile_name, profdef in self.profiles.items():
            for reobj in profdef['target_server']:
                if ( reobj.match(server_name)):
                    result = profdef['task_name']
                    if ( self.config_debug):
                        self.log(result)

        return result

    def get_config(self):
        settings = self.load_settings()
        profiles_map = OrderedDict() # profile name -> profile label
        profiles_def = OrderedDict() # profile name -> settings dict

        # main
        self.config_debug = settings.get_bool(
            "debug", section=self.CONFIG_SECTION_MAIN,
            fallback=self.DEFAULT_CONFIG_DEBUG
        )

        self.config_command_line = settings.get(
            "command_line", section=self.CONFIG_SECTION_MAIN,
            fallback=self.DEFAULT_CONFIG_COMMAND_LINE
        )

        self.config_args = settings.get(
            "args", section=self.CONFIG_SECTION_MAIN,
            fallback=self.DEFAULT_CONFIG_ARGS
        )

        self.config_bash_user = settings.get(
            "bash_user", section=self.CONFIG_SECTION_MAIN,
            fallback=self.DEFAULT_CONFIG_BASH_USER
        )

        # read profiles names and validate them
        for section_name in settings.sections():
            if not section_name.lower().startswith(self.CONFIG_SECTION_PROFILE):
                continue

            profile_label = section_name[len(self.CONFIG_SECTION_PROFILE):]
            profile_label = profile_label.strip()
            profile_name = profile_label.lower()

            if not profile_name:
                self.warn('Ignoring empty profile name (section "{}").'.format(
                    section_name))
                continue

            forbidden_chars = ":;,/|\\"
            if any(c in forbidden_chars for c in profile_label):
                self.warn((
                    'Forbidden character(s) found in profile name "{}". ' +
                    'Forbidden characters list "{}"').format(
                    profile_label, forbidden_chars))
                continue

            if profile_name in profiles_map:
                self.warn('Ignoring "{}" defined twice.'.format(
                    section_name))
                continue

            profiles_map[profile_name] = section_name

            profiles_def[profile_name] = {}
            profiles_def[profile_name]['label'] = profile_label
            profiles_def[profile_name]['target_server'] = '.+'
            profiles_def[profile_name]['task_name'] = '{Bash::bash}'

            
        # read profiles settings
        for profile_name, section_name in profiles_map.items():
            profdef = profiles_def[profile_name]

            target_server = settings.get_multiline(
                "target_server", section=section_name,
                fallback=profdef['target_server']
            )

            profdef['target_server'] = []
            for expression in target_server:
                if not expression:
                    continue
                try:
                    profdef['target_server'].append(
                        re.compile(expression))
                except Exception as exc:
                    self.warn((
                        'Ignoring invalid target_server "{}" from "{}". ' +
                        'Error: {}').format(expression, section_name, str(exc)))
                    continue

            profdef['task_name'] = settings.get(
                "task_name", section=section_name, 
                fallback=profdef['task_name']
            )

        self.profiles = profiles_def

        # print profiles settings
        # if self.config_debug and self.profiles:
        #    self._print_profiles()


