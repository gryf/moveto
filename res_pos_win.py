#! /usr/bin/env python
"""
Position/place windows in WindowMaker.
Script calculates size of the target windows depending on current screen size.

Required python 2.7

Dependencies:
    - xrandr
    - wmctrl
    - xdotool
    - xwininfo

Calculate possible moves of the window contary to the current size and
position. Assuming we have screen layout (two phisical monitors in twin view
nvidia mode which makes one big screen available)

    +---------------------+-----------------------------+--+
    |                     |                             |  |
    | +--------+          |                             +--+
    | |window  |          |                             |  |
    | |        |          |                             +--+
    | +--------+          |                             |  |
    |                     |                             +--+
    |                     |                             |  |
    |   screen 0          |   screen 1                  +--+
    |                     |                                |
    +--+                  +--+--+                          |
    |  |                  |  |  |                          |
    +--+------------------+--+--+--------------------------+

possible moves of the depicted window would be:
    1. without resizing:
        - move to the left edge of the screen 0
        - move to the right edge of the screen 0
        - move to the left edge of the screen 1
        - move to the right edge of the screen 1
        - move to the screen 1 (don't cross boundary of the
          screen)
        - move to the left edge of the screen 1
        - move to the right edge of the screen 1
    2. with resizing:
        - move to the screen 1 (maximized)
        - maximize on current screen
        - move to screen 0 to the left half
        - move to screen 0 to the right half
        - move to screen 1 to the left half
        - move to screen 1 to the right half

Author: Roman 'gryf' Dobosz <gryf73@gmail.com>
Date: 2013-01-06
Version: 1.1
"""
import os
import sys
import re
from subprocess import Popen, PIPE, call
import json

CACHE_FILENAME = "~/.cache/res_pos_win.cache"
DOCK_ON_RIGHT = True
COVER_MINIWINDOWS = False
COVER_DOCK = False
DECOTATORS_HEIGHT = 29  # TODO: get it somehow from real window


class Screens(object):
    """
    Holds entire screen information and also Screen objects as a list
    """
    def __init__(self):
        """Class container for a Screen objects and whole area coordinates"""
        self.screens = []
        self.coords = ()

    def append(self, screen):
        """Add screen"""
        self.screens.append(screen)

    def dump(self):
        """Dump object as dictionary - suitable for serialziation"""
        return {"coords": self.coords,
                "screens": [scr.dump() for scr in self.screens]}

    def load(self, data):
        """Recreate object state from provided dictionary"""
        self.screens = []
        self.coords = tuple(data["coords"])
        for scr in data['screens']:
            screen = Screen()
            screen.load(scr)
            self.screens.append(screen)

    def guess_dimensions(self, window):
        """
        Check wheter current window is in one of three states: maximized,
        left-half maximized, right-half maximized. If so, return appropriate
        information, None otherwise
        """
        for scr in self.screens:
            if window == scr.left_half:
                return "left"
            if window == scr.right_half:
                return "right"

            # check for maximized window (approximated)
            if window['pos_x'] == window['pos_y'] == 0:
                if window['size_x'] in range(scr.x - 32, scr.x + 32) and \
                        window['size_x'] in range(scr.x - 32, scr.x + 32):
                    return "maximized"

        return None

class Screen(object):
    """
    Holds separate display information. It can be separate X screen or just a
    display/monitor
    """
    def __init__(self, x=0, y=0, sx=0, sy=0):
        """Initialization"""
        self.x = int(x)
        self.y = int(y)
        self.x_shift = int(sx)
        self.y_shift = int(sy)
        self.main = False

        self.left_half = {"pos_x": 0,
                          "pos_y": 0,
                          "size_x": 0,
                          "size_y": 0}

        self.right_half = {"pos_x": 0,
                           "pos_y": 0,
                           "size_x": 0,
                           "size_y": 0}

        self.maximized = {"pos_x": 0,
                          "pos_y": 0,
                          "size_x": 0,
                          "size_y": 0}

    def calculate_columns(self):
        """
        Calculate dimension grid, which two column windows could occupy,
        make it pixel exact.
        """
        sx, sy = self.x, self.y

        if sx % 2 != 0:
            # it is rare, but hell, shit happens
            sx = sx - 1


        if self.main and not COVER_DOCK:
            # dock on the right side + 2px for border
            self.x = sx = sx - (64 + 2)

        # miniwindows on bottom + 2px for border
        if not COVER_MINIWINDOWS:
            self.y = sy = sy - (64 + 2)

        self.left_half['size_x'] = sx / 2 - 1

        self.right_half['size_x'] = sx / 2
        self.right_half['pos_x'] = sx / 2

        self.maximized['size_x'] = sx

        self.maximized['size_y'] = self.right_half['size_y'] = \
                self.left_half['size_y'] = sy - DECOTATORS_HEIGHT

    def dump(self):
        """
        Return current Screen object state as dictionary suitable for
        serialization
        """
        return {"main": self.main,
                "x": self.x,
                "y": self.y,
                "x_shift": self.x_shift,
                "y_shift": self.y_shift,
                "left_half": self.left_half,
                "right_half": self.right_half,
                "maximized": self.maximized}

    def load(self, data):
        """Restore Screen state from provided dictionary"""
        self.x = data['x']
        self.y = data['y']
        self.x_shift = data['x_shift']
        self.y_shift = data['y_shift']
        self.left_half = data['left_half']
        self.right_half = data['right_half']
        self.maximized = data['maximized']
        self.main = data['main']


class WMWindow(object):
    """
    Window object. Hold all of the information about current window and
    surrounded environment (screens and such).
    """

    screen_re = re.compile("[^,]*,\scurrent\s(\d+)\sx\s(\d+),.*")
    device_re = re.compile(".*\sconnected\s(\d+)x(\d+)\+(\d+)\+(\d+)")
    display_re = re.compile("^.*,\scurrent\s(\d+)\sx\s(\d+),\s.*$")
    position_re = re.compile("^\s+Position:\s(\d+),(\d+)\s.*$")
    geometry_re = re.compile(".*Geometry:\s(\d+)x(\d+).*")

    def __init__(self):
        """
        Initialization
        """
        self.screens = []
        self.display_size = None
        self.x = None
        self.y = None
        self.pos_x = None
        self.pos_y = None
        self.current_screen = 0
        self.state = None

        self._load_screens()
        self._get_props()

    def _load_screens(self):
        """
        Load screen form cache file or create them from scratch if cache
        doesn't exists
        """
        fname = os.path.expanduser(CACHE_FILENAME)
        if not os.path.exists(fname):
            self._discover_screens()
        else:
            with open(fname) as fp_:
                self.screens = Screens()
                self.screens.load(json.load(fp_))

    def _get_props(self):
        """
        Update current window dimensions and position
        """
        self.x = self.y = self.pos_x = self.pos_y = None


        out = Popen(['xdotool', 'getactivewindow', 'getwindowgeometry'],
                    stdout=PIPE).communicate()[0]
        out = out.strip().split("\n")

        if len(out) != 3:
            print "Cannot get window size and position"
            return

        pos, size = out[1:]

        match = self.position_re.match(pos)
        if match:
            self.pos_x, self.pos_y = match.groups()
            # XXX: arbitrary correction of the window position. Don't know why
            # xdotool reports such strange data - maybe it is connected with
            # inner/outer dimensions and/or window manager decorations
            self.pos_x = int(self.pos_x) - 1
            self.pos_y = int(self.pos_y) - 43

        match = self.geometry_re.match(size)
        if match:
            self.x, self.y = match.groups()
            self.x = int(self.x)
            self.y = int(self.y)

        if None in (self.x, self.y, self.pos_x, self.pos_y):
            print "Not enough data for calculate window placement"
            print self.x, self.y, self.pos_x, self.pos_y
        else:
            self.guess_dimensions()

    def guess_dimensions(self):
        """Wrapper for screens guess_dimensions method"""
        return self.screens.guess_dimensions(self.get_data())

    def _discover_screens(self):
        """Create list of available screens. Assuming, that first screen
        reported is main screen."""
        out = Popen(['xrandr'], stdout=PIPE).communicate()[0]
        self.screens = Screens()

        for line in out.split("\n"):
            if self.device_re.match(line):
                x, y, sx, sy = self.device_re.match(line).groups()
                screen = Screen(x, y, sx, sy)
                if not self.screens.screens:
                    screen.main = True
                screen.calculate_columns()
                self.screens.append(screen)
            match = self.display_re.match(line)
            if match:
                self.display_size = match.groups()

        fname = os.path.expanduser(CACHE_FILENAME)

        # sort screens depending on the position (only horizontal order is
        # supported)
        screens = {}

        for screen in self.screens.screens:
            screens[screen.x_shift] = screen

        self.screens.screens =  [screens[key] for key in
                                 sorted(screens.keys())]


        if not os.path.exists(fname):
            try:
                os.makedirs(os.path.dirname(fname))
            except OSError:
                pass

            try:
                with open(fname, "w") as fp:
                    json.dump(self.screens.dump(), fp)
            except (OSError, IOError) as msg:
                print "Error in creating cache file:\n", msg

    def get_data(self):
        """Return current window coordinates and size"""
        return {"pos_x": self.pos_x,
                "pos_y": self.pos_y,
                "size_x": self.x,
                "size_y": self.y}

    def move_to_screen(self, screen_direction):
        """
        Set current screen to possible next or previous. Returns true if such
        operation is possible, false otherwise.
        """

        if screen_direction == "right":
            idx = self.current_screen + 1
        else:
            idx = self.current_screen - 1

        if idx < 0:
            return False

        try:
            self.screens.screens[idx]
        except IndexError:
            return False

        self.current_screen = idx
        return True

    def full(self):
        """Maximize window"""

    def left(self, screen_direction=None):
        """Maximize to left half"""

        coords = self.screens.screens[self.current_screen].left_half
        cmd = ['xdotool', "getactivewindow",
               "windowmove", str(coords['pos_x']), str(coords['pos_y']),
               "windowsize", str(coords['size_x']), str(coords['size_y'])]
        call(cmd)

    def right(self, screen_direction=None):
        """Maximize to right half"""
        cmd = ['xdotool', "getactivewindow"]
        if screen_direction:
            if not self.move_to_screen(screen_direction):
                return

        if screen_direction:
            move = self.move_to_screen(screen_direction)
            if not move:
                return
            cmd.extend(move)

    def get_coords(self, which):
        """Return screen coordinates"""
        scr = self.screens.screens[self.current_screen]

        coord_map = {"maximized": scr.maximized,
                     "left_half": scr.left_half,
                     "right_half": scr.right_half}

        return coord_map[which]


def cycle(direction):
    """Cycle through the window states"""
    wmwin = WMWindow()
    current_state = wmwin.guess_dimensions()

    if direction == "left":
        movement = {"left": ("right_half", "left"),
                    "maximized": ("left_half", None),
                    "right": ("maximized", None),
                    None: ("left_half", None)}
    elif direction == "right":
        movement = {"left": ("maximized", None),
                    "maximized": ("right_half", None),
                    "right": ("left_half", "right"),
                    None: ("right_half", None)}

    key, direction = movement[current_state]

    if direction:
        if not wmwin.move_to_screen(direction):
            return

    coords = wmwin.get_coords(key)
    cmd = ['xdotool', "getactivewindow",
           "windowmove", str(coords['pos_x']), str(coords['pos_y']),
           "windowsize", str(coords['size_x']), str(coords['size_y'])]

    call(cmd)


def usage():
    print "usage: %s [cycle_left|cycle_right]" % sys.argv[0]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()

    if sys.argv[1] == "cycle_left":
        cycle("left")
    elif sys.argv[1] == "cycle_right":
        cycle("right")
    else:
        usage()

