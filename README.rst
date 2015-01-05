moveto
======

"Moveto" is an simple script, which is acting similar to shortcut Super-Left and
Super-Right in Windows 7, but for WindoMaker with additional stuff. To use it,
simply create the menu entries for two motions (left and right) and assign
shortcuts for them.

Features
--------

There is several thing which may be done using ``moveto.py`` script:

- Window movement.

  - Moving window around using pattern: maximized-left to fullscreen to
    maximized-right to maximized-left on next available screen on the right or
    stop. This way one can move the window across the screens in intuitive way.
  - Moved window is aware of the WindowMaker settings regarding covering dock
    and miniwindows.
  - Mouse cursor is moving along with the window.

- Move (send) mouse cursor to the specified monitor. Monitor name can
- Display currently connected and active monitors (first string (e.g. ``VGA1``,
  ``LVDS1`` and so on, is the name for the ``--monitor-name`` option)
