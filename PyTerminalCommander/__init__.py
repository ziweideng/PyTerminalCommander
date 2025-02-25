# -*- coding: utf-8 -*-

'''
Original code is from: http://zderadicka.eu/terminal-interfaces-in-python/

Great thanks to Ivan Zderadicka

Since Jun 21, 2016
@author: owwlo

=== Original File Header & LICENSE ===
Created on Aug 2, 2015
@author: ivan
===
The MIT License (MIT)

Copyright (c) 2015 Ivan Zderadicka

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
================ End =================
'''

from collections import deque
from threading import Thread
from sys import platform as _platform

import urwid.curses_display
import urwid.raw_display
import urwid.web_display

import urwid
import threading
import sys
import os
import traceback
import six

if urwid.web_display.is_web_request():
    Screen = urwid.web_display.Screen
else:
    Screen = urwid.raw_display.Screen

urwid.set_encoding("utf-8")

class PopUpDialog(urwid.WidgetWrap):
    def __init__(self, input_handler, text):
        pile = urwid.Pile([urwid.Text(text, align='center')])
        fill = urwid.Filler(pile)
        self.__super.__init__(urwid.AttrWrap(fill, 'popup'))
        self.input_handler = input_handler

    def keypress(self, size, key):
        return self.input_handler.keypress(size, key)

class CommandHandler(object):

    def __init__(self, quit_commands=['q', 'quit', 'exit'],
                 help_commands=['help', '?', 'h']):
        self._quit_cmd = quit_commands
        self._help_cmd = help_commands

    def __call__(self, commander, line):
        extras = line.split(' ', 1)
        cmd = extras[0].lower()

        if cmd in self._quit_cmd:
            cmd = 'quit'

        if cmd in self._help_cmd:
            args = (extras[1].split(' ')[0] if len(extras) > 1
                    and extras[1] else None)
            return self.help((args if args else None))
        elif hasattr(self, 'do_' + cmd):
            return getattr(self, 'do_' + cmd)(commander,
                    (extras[1] if len(extras) > 1 else None))
        else:
            commander.output('Unknown command: %s' % cmd, 'error')

    def help(self, cmd=None):

        def std_help():
            qc = '|'.join(self._quit_cmd)
            hc = '|'.join(self._help_cmd)
            res = \
                'Type [%s] command_name to get more help about particular command\n' \
                % hc
            res += 'Type [%s] to quit program\n' % qc
            cl = [name[3:] for name in dir(self)
                  if name.startswith('do_') and len(name) > 3]
            res += 'Available commands: %s' % ', '.join(sorted(cl))
            return res

        r = None
        if not cmd:
            r = std_help()
        else:
            try:
                fn = getattr(self, 'do_' + cmd)
                doc = fn.__doc__
                r = doc or 'No documentation available for %s' % cmd
            except AttributeError:
                r = std_help()

        return (r, "help_text")

class FocusMixin(object):

    def mouse_event( self, size, event, button, x, y, focus ):
        if focus and hasattr(self, '_got_focus') and self._got_focus:
            self._got_focus()
        return super(FocusMixin, self).mouse_event( size, event, button, x, y, focus )


class ListView(FocusMixin, urwid.ListBox):

    def __init__( self, model, got_focus, max_size = None, show_line_num = False, tab_spaces = 4 ):
        urwid.ListBox.__init__(self, model)
        self._got_focus = got_focus
        self.max_size = max_size
        self._lock = threading.Lock()
        self._line_counter = 0
        self.show_line_num = show_line_num
        self.tab_spaces = tab_spaces

    def add(self, line):
        if isinstance(line, six.string_types):
            line = line.replace("\t", " " * self.tab_spaces)
        elif isinstance(line, tuple):
            line = (line[0], line[1].replace("\t", " " * self.tab_spaces))

        self._line_counter += 1
        with self._lock:
            was_on_end = self.get_focus()[1] == len(self.body) - 1
            if self.max_size and len(self.body) > self.max_size:
                del self.body[0]
            if self.show_line_num:
                line = urwid.Columns([(4, urwid.Text(str(self._line_counter))),  urwid.Text(line)])
            else:
                line = urwid.Text(line)
            self.body.append(line)
            last = len(self.body) - 1
            if was_on_end:
                self.set_focus(last, 'above')

def super_move(text, position, back_forward = True, del_char = True):
    idx_inc = -1 if back_forward else 1
    end_pos = position - 1 if back_forward else position
    if end_pos >= 0 and end_pos < len(text):
        triming = False if text[end_pos].isalnum() else True
        while(end_pos >= 0 and end_pos < len(text)
              and (triming or text[end_pos].isalnum())):
            if text[end_pos].isalnum():
                triming = False
            end_pos += idx_inc
    if back_forward: end_pos += 1
    end_pos = min(len(text), end_pos)
    end_pos = max(0, end_pos)
    position = min(len(text), position)
    position = max(0, position)
    if del_char:
        text = text[:min(position, end_pos)] + text[max(position, end_pos):]
    r_pos = end_pos if not del_char else end_pos if back_forward else position
    return text, r_pos

class Input(FocusMixin, urwid.Edit):

    signals = ['line_entered']

    def __init__(self, got_focus=None):
        urwid.Edit.__init__(self, allow_tab = False)
        self.history = deque(maxlen=1000)
        self._history_index = -1
        self._got_focus = got_focus

    def keypress(self, size, key):
        if key == 'enter':
            line = self.edit_text.strip()
            self.edit_text = u''
            if line:
                urwid.emit_signal(self, 'line_entered', line)
                self.history.append(line)
            self._history_index = len(self.history)
        elif key == 'up':

            self._history_index -= 1
            if self._history_index < 0:
                self._history_index = 0
            else:
                self.edit_text = self.history[self._history_index]
        elif key == 'down':
            self._history_index += 1
            if self._history_index >= len(self.history):
                self._history_index = len(self.history)
                self.edit_text = u''
            else:
                self.edit_text = self.history[self._history_index]
        elif key in ["ctrl right", "ctrl left", "meta backspace"]:
            keys = key.split(" ")
            back_forward = False if keys[1] == "right" else True
            del_char = True if keys[1] == "backspace" else False
            new_text, new_pos = super_move(self.edit_text, self.edit_pos, back_forward, del_char)
            self.set_edit_text(new_text)
            self.set_edit_pos(new_pos)
        else:
            if key == "ctrl a":
                key = "home"
            elif key == "ctrl e":
                key = "end"
            urwid.Edit.keypress(self, size, key)

class CommanderPopupLauncher(urwid.PopUpLauncher):
    WIDTH = 60
    HEIGHT = 3

    DEFAULT_DURATION = 3

    def __init__(self, widget, commander):
        self.__super.__init__(widget)
        self.commander = commander
        self.duration = CommanderPopupLauncher.DEFAULT_DURATION

    def notify(self, text, duration):
        self.duration = duration
        self.pop_up = PopUpDialog(self.commander, text)
        self.open_pop_up()

    def create_pop_up(self):
        # Setup timeout timer
        self.commander.eloop.set_alarm_in(self.duration, lambda x, y: self.close_pop_up())

        return self.pop_up

    def get_pop_up_parameters(self):
        screen = Screen()
        width, height = screen.get_cols_rows()
        return {
            'left': int((width - CommanderPopupLauncher.WIDTH) / 2),
            'top': int((height - CommanderPopupLauncher.HEIGHT) / 2),
            'overlay_width': CommanderPopupLauncher.WIDTH,
            'overlay_height': CommanderPopupLauncher.HEIGHT
        }

class Commander(urwid.Frame):

    DEFAULT_COMMAND_CAPTION = u"Command:  (Tab to switch focus to upper frame, where you can scroll text)"

    class Exit(object):
        pass

    PALLETE = [
        ('inactive_title', urwid.BLACK, urwid.LIGHT_GRAY),
        ('active_title', urwid.WHITE, urwid.DARK_BLUE),
        ('normal', urwid.LIGHT_GRAY, urwid.BLACK),
        ('error', urwid.LIGHT_RED, urwid.BLACK),
        ('help_text', urwid.YELLOW, urwid.BLACK),
        ('popup', urwid.WHITE, urwid.DARK_BLUE),
    ]

    def __init__( self, title, command_caption=DEFAULT_COMMAND_CAPTION
        , cmd_cb=None
        , max_size=2048
        , show_help_on_start = False
        , hook_stdout = False, hook_stderr = False
        , extra_pallete = None
        , show_line_num = False
        , spaces_for_tab = 4 ):
        self._show_help_on_start = show_help_on_start
        self._hook_stdout = hook_stdout
        self._hook_stderr = hook_stderr


        # Used to keep the old out streams
        self._old_stdout = None
        self._old_stderr = None

        self.header = urwid.AttrWrap(urwid.Text(title), 'inactive_title')
        self.foot = urwid.AttrMap(urwid.Text(command_caption), 'active_title')

        self.model = urwid.SimpleListWalker([])
        self.inner = ListView(self.model, lambda : \
                             self._update_focus(False),
                             max_size=max_size, show_line_num = show_line_num, tab_spaces = spaces_for_tab)
        self.popup_launcher = CommanderPopupLauncher(self.inner, self)
        self.input = Input(lambda : self._update_focus(True))
        foot = urwid.Pile([self.foot, urwid.AttrMap(self.input, 'normal')])

        urwid.Frame.__init__(self, urwid.AttrWrap(self.popup_launcher, 'normal'), header = self.header, footer = foot)

        self.set_focus_path(['footer', 1])
        self._focus = True
        urwid.connect_signal(self.input, 'line_entered',
                             self.on_line_entered)
        self._cmd = cmd_cb
        self.eloop = None

        if extra_pallete:
            self.PALLETE.extend(extra_pallete)

        self._output_styles = [s[0] for s in self.PALLETE]

    def loop(self, handle_mouse=False):
        self.eloop = urwid.MainLoop(self, self.PALLETE, handle_mouse=handle_mouse, pop_ups=True)
        self._eloop_thread = threading.current_thread()

        if self._show_help_on_start:
            self.eloop.set_alarm_in(0., lambda x, y: self.output(*self._cmd.help(None)))

        self._hookToStdOutput(hookToStdOut = self._hook_stdout, hookToStdErr = self._hook_stderr)

        try:
            self.eloop.run()
        except Exception as e:
            self._hookToStdOutput(hookToStdOut = False, hookToStdErr = False)
            print(traceback.format_exc())

    def on_line_entered(self, line):
        if self._cmd:
            try:
                res = self._cmd(self, line)
            except Exception as e:
                traceback.print_exc()
                self.output('Error: %s' % e, 'error')
                return
            if res == Commander.Exit:
                raise urwid.ExitMainLoop()
            elif res:
                if isinstance(res, tuple):
                    self.output(str(res[0]), style = res[1])
                else:
                    self.output(str(res))
        else:
            if line in ('q', 'quit', 'exit'):
                raise urwid.ExitMainLoop()
            else:
                self.output(line)

    def redraw(self):
        if self.eloop and self._eloop_thread \
            != threading.current_thread():
            self.eloop.draw_screen()

    def output(self, line, style=None):
        if style and style in self._output_styles:
            line = (style, line)
        self.inner.add(line)
        # since output could be called asynchronously form other threads we need to refresh screen in these cases
        self.redraw()

    def getStdOutpoutStream(self, is_stderr=False):
        commander = self

        class StdOutput:

            def __init__(self, is_stderr=is_stderr,
                         commander=commander):
                self.is_stderr = is_stderr
                self.commander = commander

            def write(self, lines):
                for line in lines.split(os.linesep):
                    if line:
                        self.commander.output(line, style=('error'
                                 if self.is_stderr else 'normal'))

        return StdOutput()

    def _update_focus(self, focus):
        self._focus = focus

    def switch_focus(self):
        if self._focus:
            self.set_focus('body')
            self._focus = False
            self.eloop.draw_screen()
            self.header.set_attr_map({None: 'active_title'})
            self.foot.set_attr_map({None: 'inactive_title'})
        else:
            self.set_focus_path(['footer', 1])
            self._focus = True
            self.header.set_attr_map({None: 'inactive_title'})
            self.foot.set_attr_map({None: 'active_title'})

    def notify(self, txt, duration = CommanderPopupLauncher.DEFAULT_DURATION):
        self.popup_launcher.notify(txt, duration)

    def keypress(self, size, key):
        if key == 'tab':
            self.switch_focus()
        return urwid.Frame.keypress(self, size, key)

    def _hookToStdOutput(self, hookToStdOut=True, hookToStdErr=True):
        if hookToStdOut:
            if self._old_stdout:
                pass
            else:
                self._old_stdout = sys.stdout
                sys.stdout = self.getStdOutpoutStream(is_stderr=False)
        else:
            if self._old_stdout:
                sys.stdout = self._old_stdout
                self._old_stdout = None
            else:
                pass
        if hookToStdErr:
            if self._old_stderr:
                pass
            else:
                self._old_stderr = sys.stderr
                sys.stderr = self.getStdOutpoutStream(is_stderr=True)
        else:
            if self._old_stderr:
                sys.stderr = self._old_stderr
                self._old_stderr = None
            else:
                pass
