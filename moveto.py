#! /usr/bin/env python
"""
Position/place windows in WindowMaker.
Script calculates size of the target windows depending on current screen size.

Required python 2.7

Dependencies:
    - pygtk
    - docopt
    - wmctrl
    - xdotool
    - xwininfo

Calculate possible moves of the window against to the current size and
position. Assuming we have screen layout (two physical monitors in twin view
nvidia mode which makes one big screen available)

To illustrate the behaviour, lets analyze following layout. Note, the window
is not maximized:

    +---------------------+-----------------------------+--+
    |                     |                             |  |
    | +--------+          |                             +--+
    | |window  |          |                             |  |
    | |        |          |                             +--+
    | +--------+          |                             |  |
    |                     |                             +--+
    |                     |                             |  |
    |                     |                             +--+
    |                     |                                |
    +--+                  +--+--+                          |
    |  |         screen 0 |  |  |                 screen 1 |
    +--+------------------+--+--+--------------------------+

Possible moves of the depicted window would be:
    - 'move left' will move window to to the left half on screen 0
    - 'move right' will move window to to the right half on screen 0

Let's assume that we chose the latter, so the new layout would be as follow:

    +----------+----------+-----------------------------+--+
    |          | window   |                             |  |
    |          |          |                             +--+
    |          |          |                             |  |
    |          |          |                             +--+
    |          |          |                             |  |
    |          |          |                             +--+
    |          |          |                             |  |
    |          |          |                             +--+
    |          |          |                                |
    +--+       +----------+--+--+                          |
    |  |         screen 0 |  |  |                 screen 1 |
    +--+------------------+--+--+--------------------------+

The possibilities are:
    - 'move left' will maximize window on screen 0
    - 'move right' will move window to to the left half on screen 1

Move right will end up with following layout. Note, that mouse cursor follow
the window, so possible child windows of the current window should appear on
the screen, where main window is.

    +---------------------+--------------+--------------+--+
    |                     | window       |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |                 |
    +--+                  +--+--+--------+                 |
    |  |         screen 0 |  |  |                 screen 1 |
    +--+------------------+--+--+--------------------------+

Again, the possibilities are:
    - 'move left' will move window to to the right half on screen 0
    - 'move right' will maximize window on screen 1


And, if user keeps pushing window to the right it will need just two more
steps to end up like this:

    +---------------------+-----------------------------+--+
    |                     | window                      |  |
    |                     |                             +--+
    |                     |                             |  |
    |                     |                             +--+
    |                     |                             |  |
    |                     |                             +--+
    |                     |                             |  |
    |                     |                             +--+
    |                     |                             |  |
    +--+                  +--+--+-----------------------+  |
    |  |         screen 0 |  |  |                 screen 1 |
    +--+------------------+--+--+--------------------------+

    +---------------------+--------------+--------------+--+
    |                     |              | window       |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    |                     |              |              +--+
    |                     |              |              |  |
    +--+                  +--+--+        +--------------+  |
    |  |         screen 0 |  |  |                 screen 1 |
    +--+------------------+--+--+--------------------------+

Further moving window to the right will have no effect.

TODO: Make it more flexible with different screen configurations

Author: Roman "gryf" Dobosz <gryf73@gmail.com>
Date: 2013-01-06
Date: 2014-03-31 (used pygtk instead of xrandr, which is faster)
Date: 2014-06-25 added docopt, corrections and simplify the process
Version: 1.3
"""
import sys
import os
import re
from subprocess import Popen, PIPE, call
import logging

from docopt import docopt
from gtk import gdk


# TODO: Make it configurable (lots of options starting from ini file)
COVER_MINIWINDOWS = True
COVER_DOCK = False
DECOTATORS_HEIGHT = 29  # TODO: get it somehow from real window

logging.basicConfig(filename=os.path.expanduser('~/moveto.log'),
                    format='%(funcName)s:%(lineno)d %(message)s',
                    level=logging.INFO)


def get_window_name():
    """Return the current active window name"""

    name = Popen(["xdotool", "getactivewindow", "getwindowname"],
                      stdout=PIPE).communicate()[0]
    name = name.strip()
    logging.debug('window name: %s', name)
    return name


def get_monitors():
    """Get monitors information:
        name
        index
        dimensions (as a tuple position x, y and dimension x and y)"""

    monitors = {}
    gdk_screen = gdk.screen_get_default()

    for out_num in range(gdk_screen.get_n_monitors()):
        monitor = {"index": out_num}
        (monitor["sx"], monitor["sy"],
         monitor["x"], monitor["y"]) = gdk_screen.get_monitor_geometry(out_num)
        monitors[gdk_screen.get_monitor_plug_name(out_num)] = monitor

    return monitors


def set_cover():
    """read actual wmaker config and set apropriate globals"""
    global COVER_MINIWINDOWS, COVER_DOCK

    with open(os.path.expanduser("~/GNUstep/Defaults/WindowMaker")) as fobj:
        for line in fobj:
            if "NoWindowOverIcons" in line and "YES" in line:
                COVER_MINIWINDOWS = False
                continue

            if "NoWindowOverDock" in line and "NO" in line:
                COVER_DOCK = True
                continue


class Screens(object):
    """
    Holds entire screen information and also Screen objects as a list
    """
    def __init__(self):
        """Class container for a Screen objects and whole area coordinates"""
        self.screens = []
        self.coords = ()
        self.dimension = None

    def append(self, screen):
        """Add screen"""
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
            if window["pos_x"] == window["pos_y"] == 0:
                if window["size_x"] in range(scr.x - 32, scr.x + 32) and \
                        window["size_x"] in range(scr.x - 32, scr.x + 32):
                    return "maximized"

        return None


class Screen(object):
    """
    Holds separate display information. It can be separate X screen or just a
    display/monitor
    """
    misbehaving_windows = ["Oracle VM VirtualBox", "LibreOffice"]

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

    def calculate_columns(self, window_name):
        """
        Calculate dimension grid, which two column windows could occupy,
        make it pixel exact.
        """
        sx, sy = self.x, self.y
        logging.debug('sx, and sy: %d, %d', sx, sy)

        if sx % 2 != 0:
            # it is rare, but hell, shit happens
            sx = sx - 1

        if self.main and not COVER_DOCK:
            # dock on the right side + 2px for border
            self.x = sx = sx - (64 + 2)
        else:
            self.x = sx = sx - 2

        # miniwindows on bottom + 2px for border
        logging.debug("Covering miniwindows: %s", COVER_MINIWINDOWS)
        if not COVER_MINIWINDOWS:
            self.y = sy = sy - (64 + 2)

        self.left_half["size_x"] = sx / 2 - 1
        self.maximized["pos_x"] = self.left_half["pos_x"] = self.x_shift

        self.right_half["size_x"] = sx / 2
        self.right_half["pos_x"] = sx / 2 + self.x_shift

        self.maximized["size_x"] = sx

        self.maximized["size_y"] = self.right_half["size_y"] = \
                self.left_half["size_y"] = sy - DECOTATORS_HEIGHT

        for name in self.misbehaving_windows:
            if name in window_name:
                logging.debug('Correcting position of window %s off 21 '
                              'pixels', window_name)
                self.left_half["pos_y"] = 21
                self.right_half["pos_y"] = 21
                self.right_half["pos_y"] = 21

        logging.debug('left half: %s', self.left_half)
        logging.debug('right half: %s', self.right_half)
        logging.debug('maximized: %s', self.maximized)

class WMWindow(object):
    """
    Window object. Hold all of the information about current window and
    surrounded environment (screens and such).
    """

    position_re = re.compile("^\s+Position:\s(\d+),(\d+)\s.*$")
    geometry_re = re.compile(".*Geometry:\s(\d+)x(\d+).*")

    def __init__(self, monitors, main):
        """
        Initialization
        """
        self.screens = []
        self.x = None
        self.y = None
        self.pos_x = None
        self.pos_y = None
        self.current_screen = 0
        self.state = None
        self._main = main
        self.name = get_window_name()

        self._discover_screens(monitors)
        self._get_props()

    def _get_props(self):
        """
        Update current window dimensions and position
        """
        self.x = self.y = self.pos_x = self.pos_y = None

        out = Popen(["xdotool", "getactivewindow", "getwindowgeometry"],
                    stdout=PIPE).communicate()[0]
        out = out.strip().split("\n")

        if len(out) != 3:
            logging.warning('Cannot get window size and position for %s',
                            self.name)
            return

        pos, size = out[1:]

        match = self.position_re.match(pos)
        if match:
            self.pos_x, self.pos_y = match.groups()
            # XXX: arbitrary correction of the window position. Don't know why
            # xdotool reports such strange data - maybe it is connected with
            # inner/outer dimensions and/or window manager decorations
            logging.debug('window position reported via xdotool: %s x %s',
                          self.pos_x, self.pos_y)
            self.pos_x = int(self.pos_x) - 1
            self.pos_y = int(self.pos_y) - 43
            logging.debug('window position after corrections: %s x %s',
                          self.pos_x, self.pos_y)

            for scr_no, scr in enumerate(self.screens.screens):
                if self.pos_x in range(scr.x_shift, scr.x + scr.x_shift):
                    self.current_screen = scr_no
                    break

        match = self.geometry_re.match(size)
        if match:
            self.x, self.y = match.groups()
            self.x = int(self.x)
            self.y = int(self.y)

        if None in (self.x, self.y, self.pos_x, self.pos_y):
            logging.warning('Not enough data for calculate window placement. '
                            'Window name "%s", (x, y, pos_x, pos_y): '
                            '%d, %d, %d, %d', self.name, self.x, self.y,
                            self.pos_x, self.pos_y)
        else:
            self.guess_dimensions()

    def guess_dimensions(self):
        """Wrapper for screens guess_dimensions method"""
        return self.screens.guess_dimensions(self.get_data())

    def _discover_screens(self, monitors):
        """Create list of available screens. Assuming, that first screen
        reported is main screen."""

        self.screens = Screens()

        for name, data in monitors.items():
            screen = Screen(data["x"], data["y"], data["sx"], data["sy"])
            if self._main and len(monitors.keys()) > 1:
                if self._main == name:
                    screen.main = True
            elif not self.screens.screens:
                screen.main = True

            screen.calculate_columns(self.name)
            self.screens.append(screen)

        # sort screens depending on the position (only horizontal order is
        # supported)
        screens = {}

        for screen in self.screens.screens:
            screens[screen.x_shift] = screen

        self.screens.screens = [screens[key] for key in sorted(screens.keys())]

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

    def get_coords(self, which):
        """Return window in screen coordinates"""
        scr = self.screens.screens[self.current_screen]

        coord_map = {"maximized": scr.maximized,
                     "left_half": scr.left_half,
                     "right_half": scr.right_half}

        return coord_map[which]


def cycle(monitors, right=False, main=None):
    """Cycle through the window states"""
    wmwin = WMWindow(monitors, main)
    current_state = wmwin.guess_dimensions()

    direction = "right" if right else "left"

    if direction == "left":
        movement = {"left": ("right_half", "left", False),
                    "maximized": ("left_half", None, False),
                    "right": ("maximized", None, True),
                    None: ("left_half", None, False)}
    elif direction == "right":
        movement = {"left": ("maximized", None, False),
                    "maximized": ("right_half", None, True),
                    "right": ("left_half", "right", False),
                    None: ("right_half", None, False)}

    key, direction, order = movement[current_state]

    if direction:
        if not wmwin.move_to_screen(direction):
            return

    coords = wmwin.get_coords(key)
    if order:
        cmd = ["xdotool", "getactivewindow",
               "windowsize", str(coords["size_x"]), str(coords["size_y"]),
               "windowmove", str(coords["pos_x"]), str(coords["pos_y"]),
               "mousemove", str(coords["pos_x"] + coords["size_x"] / 2),
               str(coords["pos_y"] + coords["size_y"] / 2)]
    else:
        cmd = ["xdotool", "getactivewindow",
           "windowmove", str(coords["pos_x"]), str(coords["pos_y"]),
           "windowsize", str(coords["size_x"]), str(coords["size_y"]),
           "mousemove", str(coords["pos_x"] + coords["size_x"] / 2),
           str(coords["pos_y"] + coords["size_y"] / 2)]

    call(cmd)


def show_monitors(monitors):
    """Print out available monitors"""
    print "Available monitors:"
    for name, data in monitors.items():
        mon = data.copy()
        mon.update({"name": name})
        print "%(name)s at %(sx)sx%(sy)s with dimensions %(x)sx%(y)s" % mon


def move_mouse(monitors, name):
    """Move the mosue pointer to the left upper corner oft the specified by
    the name screen"""
    mon = monitors.get(name)

    if not mon:
        print "No such monitor: %s" % name
        return

    posx = mon["sx"] + 15
    posy = mon["sy"] + 50
    cmd = ["xdotool", "mousemove", str(posx), str(posy)]
    call(cmd)


def main():
    """get the arguments, run the app"""
    arguments = """Move windows around mimicking Windows7 flag+arrows behaviour

Usage:
  %(prog)s move (left|right) [-r|-l] [-m NAME]
  %(prog)s mousemove -m NAME
  %(prog)s showmonitors
  %(prog)s (-h | --help)
  %(prog)s --version

Options:
  -m NAME --monitor-name=NAME  Name of the monitor to be treades as the main
                               one (so the one containing dock)
  -r --dock-right              Dock is on the right edge of the rightmost
                               screen
  -l --dock-left               Dock is on the left edge of the leftmost screen
  -h --help                    Show this screen.
  -v --version                 Show version.

""" % {"prog": sys.argv[0]}
    opts = docopt(arguments, version=0.1)
    monitors = get_monitors()

    if opts["showmonitors"]:
        show_monitors(monitors)
        return

    if opts["mousemove"]:
        move_mouse(monitors, opts["--monitor-name"])
        return

    if opts["move"]:
        set_cover()
        cycle(monitors, bool(opts["right"]), main=opts["--monitor-name"])


if __name__ == "__main__":
    main()
