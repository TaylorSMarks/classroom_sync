import logging
import requests

from collections        import namedtuple
from contextlib         import suppress
from getpass            import getuser
from re                 import DOTALL, IGNORECASE, compile as Regex
from thonny             import get_workbench
from thonny.codeview    import CodeView
from thonny.shell       import ShellView
from time               import time, ctime
from tkinter            import _default_root, Menu, DISABLED, NORMAL
from tkinter.messagebox import showinfo
from traceback          import format_exc
from threading          import Timer

copyablePattern = Regex(r'#\s*COPYABLE.*?#\s*END\s*COPYABLE', DOTALL | IGNORECASE)

# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
# 
# To Install:
#   1a - Windows: Need to install git first - can get it from here: https://git-scm.com/download/win
#   1b - Mac: Prefix the below command with sudo. It will prompt for the password (which won't be shown) after. May have to install Xcode command line tools if prompted.
#   2  - Everyone: pip3 install git+https://github.com/TaylorSMarks/classroom_sync.git
#
# REQUIRED STEPS LEFT:
#  1 - Selecting stuff to highlight is difficult on the Mac - requires a right click to focus the widget, first. Fix it so left click always works for highlighting on the Mac.
#  2 - Illegal content is sometimes allowed on the clipboard? I don't know what I did to get around the checker...
#      I wonder if maybe the checker is sensitive to linebreak types?
#
# BUGS SOMETIMES SEEN:
#  1 - Shutdown sometimes hangs on the Mac, or the window closes but the application keeps running on Windows.  <<< Possibly related to closing with unsaved files?
#  2 - Shell syncing sometimes just doesn't seem to happen?
#  3 - Explicitly picking something to view doesn't always work? <<< I think I prioritized a file from Windows, then the Mac couldn't request another?
#  4 - Files vanish after they're ten minutes old and never show up again?
#
# OPTIONAL STEPS LEFT:
#  1 - Fix inconsistent font issues in CodeMirrorView.  <<< Seems to be related to it not viewing everything as code? Probably doesn't matter since we shouldn't edit it anyways.
#  2 - Fix the weird scroll bar in CodeMirrorView.
#  3 - Add an ability to un-request files.
#  4 - Add in an assistant mirror view.
#  
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

class ShellMirrorView(CodeView):
    def __init__(self, *args, **kwargs):
        # Syntax highlighting here should be different from a normal CodeView... maybe? Or maybe it really doesn't matter, as long as it's disabled?
        kwargs['state'] = DISABLED
        super().__init__(*args, **kwargs)

class CodeMirrorView(CodeView):
    def __init__(self, *args, **kwargs):
        kwargs['line_numbers'] = True
        kwargs['font'] = 'EditorFont'
        kwargs['state'] = DISABLED
        super().__init__(*args, **kwargs)

SentFile = namedtuple('SentFile', ['contents', 'time'])

def updateRequestedFile(username, file):
    sync.requestUser, sync.requestFile = username, file

def updatePrioritizeFile(filename):
    logging.info('Set prioritize file to: ' + filename)
    sync.prioritizeFile = filename

def requestablePairToName(username, file):
    return "{}'s {}".format(username, file)

def updateMenu(wb):
    syncMenu = wb.get_menu('Classroom Sync')

    if not hasattr(updateMenu, 'viewMenu'):
        updateMenu.viewMenu = Menu(syncMenu, tearoff = 0)
        syncMenu.add_cascade(label = 'View Remote...', menu = updateMenu.viewMenu)

    if not hasattr(updateMenu, 'showMenu'):
        updateMenu.showMenu = Menu(syncMenu, tearoff = 0)
        syncMenu.add_cascade(label = 'Show Everyone...', menu = updateMenu.showMenu)

    currentRequestables = [f for f in sync.requestableFiles]

    # Remove everything that was requestable, but isn't anymore.
    for oldRequestable in updateMenu.oldRequestable:
        if oldRequestable not in currentRequestables:
            updateMenu.viewMenu.delete(updateMenu.viewMenu.index(requestablePairToName(*oldRequestable)))

    # Add everything new that's now requestable.
    for newRequestable in currentRequestables:
        if newRequestable not in updateMenu.oldRequestable:
            updateMenu.viewMenu.add_command(label = requestablePairToName(*newRequestable), command = lambda: updateRequestedFile(*newRequestable))

    updateMenu.oldRequestable = currentRequestables

    currentFiles = [f for f in getAllFiles(wb)]

    # Remove everything that was sharable, but isn't anymore.
    for oldFile in updateMenu.oldSharable:
        if oldFile not in currentFiles:
            updateMenu.showMenu.delete(updateMenu.showMenu.index(oldFile))

    # Add everything new that's now sharable.
    for filename in currentFiles:
        if filename not in updateMenu.oldSharable:
            updateMenu.showMenu.add_command(label = filename, command = lambda: updatePrioritizeFile(filename))

    updateMenu.oldSharable = currentFiles

updateMenu.oldRequestable = []
updateMenu.oldSharable    = []

def getAllFiles(wb):
    allFiles = {}
    editors  = wb.get_editor_notebook().get_all_editors()

    for e in editors:
        baseFilename = e.get_title()
        if e.is_modified() and baseFilename.endswith('*'):
            baseFilename = baseFilename[:-1]

        baseFilename = filename = baseFilename.strip()

        number = 1
        while filename in allFiles:
            filename = baseFilename + '-' + str(number)
            number += 1

        allFiles[filename] = e.get_code_view().get_content()

    return allFiles

def sync():
    wb           = get_workbench()
    allFiles     = getAllFiles(wb)
    changedFiles = {}

    def addIfChanged(name, contents, building):
        ''' Adds to building if the contents have changed since last sent,
            or if they haven't been sent in the past 10 minutes. '''
        if (name not in sync.lastSentFiles
                or sync.lastSentFiles[name].contents != contents
                or sync.lastSentFiles[name].time     <= time() - 600):
            building[name] = contents

    for filename in allFiles:
        addIfChanged(filename, allFiles[filename], changedFiles)

    shellContents = ''
    with suppress(Exception):
        shellContents = wb.get_view('ShellView').text.get('1.0', 'end-1c')

    addIfChanged(':shell:', shellContents, changedFiles)

    clipboardEnforcer.copyableText['files'] = ''.join(allFiles.values()) + shellContents

    request = {'user': getuser()}

    if changedFiles:
        request['files'] = changedFiles

    for var in 'lastVersion', 'lastUser', 'lastFile', 'prioritizeFile', 'requestUser', 'requestFile', 'lastShell':
        val = getattr(sync, var)
        if val is not None:
            request[var] = val
            if var == 'prioritizeFile':
                sync.prioritizeFile = None  # Only declare it as a priority once.

    try:
        r = requests.post('https://marksfam.com/class_sync/class_sync', json = request)

        try:
            response = r.json()
        except Exception:
            logging.exception('Failed to convert from json: ' + r.text)
            raise

        for f in changedFiles:
            sync.lastSentFiles[f] = SentFile(changedFiles[f], time())

        sync.requestableFiles = response['files']
        updateMenu(wb)

        def syncHelper(viewName, tabName, contents, syncKey):
            wb.show_view(viewName, False)  # Don't take the focus.

            view     = wb.get_view(viewName)
            notebook = view.home_widget.master  # Instance of ttk.Notebook
            notebook.tab(view.home_widget, text = tabName)

            viewText = view.text
            viewText['state'] = NORMAL
            viewText.set_content(contents)
            viewText['state'] = DISABLED

            clipboardEnforcer.syncText[syncKey] = contents

        if 'version' in response:
            sync.lastVersion = response['version']
            sync.lastUser    = response['user']
            sync.lastFile    = response['file']
            syncHelper('CodeMirrorView', 'Code Mirror - ' + requestablePairToName(sync.lastUser, sync.lastFile), response['body'], 'main')
            clipboardEnforcer.copyableText['allowed'] = ''.join(copyablePattern.findall(response['body']))

        if 'shellVersion' in response:
            sync.lastShell = response['shellVersion']
            sync.lastUser  = response['user']
            logging.info('Received shell version ' + str(sync.lastShell) + ' from ' + sync.lastUser)
            syncHelper('ShellMirrorView', sync.lastUser + "'s Shell", response['shellBody'], 'shell')
    except Exception:
        logging.exception('Failure during sync.', exc_info = True)
    finally:
        if not get_workbench()._closing:
            logging.info('Will kick off another sync in 5 seconds since there is no mention of the app closing as of: ' + ctime())
            Timer(5, sync).start()
        else:
            logging.info('No more syncing - time for the app to die: ' + ctime())

sync.requestableFiles = []
sync.lastSentFiles    = {}
sync.lastVersion      = None
sync.lastUser         = None
sync.lastFile         = None
sync.lastShell        = None
sync.prioritizeFile   = None
sync.requestUser      = None
sync.requestFile      = None

def clipboardEnforcer():
    try:
        clipboardContents = _default_root.clipboard_get()
        if clipboardContents != clipboardEnforcer.previousClipboardContents:
            stripped = clipboardContents.strip()
            if any(stripped in t for t in clipboardEnforcer.syncText.values()) and not any(stripped in t for t in clipboardEnforcer.copyableText.values()):
                _default_root.clipboard_clear()
                _default_root.clipboard_append(clipboardEnforcer.previousClipboardContents)
                showinfo('Forbidden copy detected!', "You weren't allowed to copy that! Your clipboard has been rolled back!")
            else:
                clipboardEnforcer.previousClipboardContents = clipboardContents
    except:
        get_workbench().report_exception("Clipboard enforcer got an error.")
    finally:
        if not get_workbench()._closing:
            clipboardEnforcer.counter += 1
            if clipboardEnforcer.counter > 30:
                clipboardEnforcer.counter = 0
                logging.info('Clipboard enforcer is still running since there is no mention of the app closing as of: ' + ctime())
            _default_root.after(200, clipboardEnforcer)
        else:
            logging.info('No more clipboard enforcing - time for the app to die: ' + ctime())

clipboardEnforcer.counter      = 0
clipboardEnforcer.syncText     = {}
clipboardEnforcer.copyableText = {}

def afterLoad():
    try:
        clipboardEnforcer.previousClipboardContents = _default_root.clipboard_get()
    except:
        clipboardEnforcer.previousClipboardContents = '<Failed to load clipboard.>'
        get_workbench().report_exception("Failed to get the clipboard while loading the plugin.")

    try:
        sync()
        clipboardEnforcer()
        logging.info('Finished loading classroom_sharing.py')
    except:
        get_workbench().report_exception("Error while loading the plugin.")
    

def load_plugin():
    logging.info('Loading classroom_sharing.py - will involve a 7 second wait.')
    wb = get_workbench()
    wb.add_view(CodeMirrorView,  'Code Mirror',  'ne', visible_by_default = True)
    wb.add_view(ShellMirrorView, 'Shell Mirror', 'se', visible_by_default = True)
    _default_root.after(7000, afterLoad)  # Give Thonny some time (7 seconds) to finish initializing
