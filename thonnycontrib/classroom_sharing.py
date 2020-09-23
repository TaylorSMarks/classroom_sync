import logging
import requests

from collections        import namedtuple
from contextlib         import suppress
from getpass            import getuser
from re                 import DOTALL, IGNORECASE, MULTILINE, compile as Regex
from time               import time, ctime
from tkinter            import _default_root, Label, Menu, PhotoImage, BOTH, DISABLED, END, NORMAL, RIGHT
from tkinter.messagebox import showinfo
from tkinter.ttk        import Frame
from threading          import Timer

try:
    from thonny          import get_workbench
    from thonny.codeview import CodeView
    from thonny.shell    import ShellView

    class ShellMirrorView(CodeView):  # CodeView(tktextext.EnhancedTextFrame(tktextext.TextFrame(ttk.Frame)))
        def __init__(self, *args, **kwargs):
            # Syntax highlighting here should be different from a normal CodeView... maybe? Or maybe it really doesn't matter, as long as it's disabled?
            kwargs['state'] = DISABLED
            super().__init__(*args, **kwargs)
            self.text.bind('<1>', lambda event: self.text.focus_set())
    
        def destroy(self):
            self.text.unbind('<1>')
            super().destroy()
    
    class CodeMirrorView(ShellMirrorView):
        def __init__(self, *args, **kwargs):
            kwargs['line_numbers'] = True
            kwargs['font'] = 'EditorFont'
            super().__init__(*args, **kwargs)

except ImportError:
    # We're probably running unit tests outside of Thonny, so it's fine.
    pass

copyablePattern = Regex(r'#\s*COPYABLE.*?#\s*END\s*COPYABLE', DOTALL | IGNORECASE)
blurCharPattern = Regex(r'\w')
blurLinePattern = Regex(r'^(.+)#\s*BLUR(\s*)$', IGNORECASE | MULTILINE)

# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
# 
# Logs go to Thonny/frontend.log in ~/Library (mac) or ~\AppData\Roaming (win)
# This file gets installed in ~\AppData\Roaming\Python\Python37\site-packages\thonnycontrib (win)
# or in /Applications/Thonny.app/Contents/Frameworks/Python.framework/Versions/3.7/lib/python3.7/site-packages
#
# To Install:
#   1a - Windows: Need to install git first - can get it from here: https://git-scm.com/download/win
#   1b - Mac: Prefix the below command with sudo. It will prompt for the password (which won't be shown) after. May have to install Xcode command line tools if prompted.
#   2  - Everyone: pip3 install git+https://github.com/TaylorSMarks/classroom_sync.git
#
# BUGS SOMETIMES SEEN:
#  1 - Shutdown sometimes hangs on the Mac, or the window closes but the application keeps running on Windows.
#       - Might have something to do with unsaved files?
#       - Might have been because I lacked a destroy method for the mirror views?
#  2 - Explicitly picking something to view doesn't always work? <<< I think I prioritized a file from Windows, then the Mac couldn't request another?
#      ^^^ This occurred for both Nicole and Matt during Lesson 4. I must figure this out immediately.
#          There's also periodically a popup about clipboard enforcer failing?
#  3 - Files vanish after they're ten minutes old and never show up again?
#
# OPTIONAL STEPS LEFT:
#  1 - Fix inconsistent font issues in CodeMirrorView.  <<< Seems to be related to it not viewing everything as code? Probably doesn't matter since we shouldn't edit it anyways.
#  2 - Fix the weird scroll bar in CodeMirrorView.
#  3 - Add an ability to un-request files.
#  4 - Add in an assistant mirror view.
#  
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

class ImageView(Frame):
    # What I have written here worked - I just decided uploading/downloading
    # images would be pretty complicated and that I could get most of the same
    # benefits from the blur function for much lesser complexity.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TODO: Make it possible to change the image.
        self.image = PhotoImage(file = r'C:\Users\Taylor\Downloads\fuckyou.gif')
        self.label = Label(self, bg = 'pink', image = self.image)
        self.label.pack(side = RIGHT, fill = BOTH, expand = True)

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

def blur(unblurredContents):
    def blurLine(unblurredLine):
        return blurCharPattern.sub('_', unblurredLine.group(1)) + unblurredLine.group(2)
    return blurLinePattern.sub(blurLine, unblurredContents)

def syncHelper(wb, viewName, tabName, contents, syncKey, scrollToEnd = False):
    wb.show_view(viewName, False)  # Don't take the focus.

    view     = wb.get_view(viewName)
    notebook = view.home_widget.master  # Instance of ttk.Notebook
    notebook.tab(view.home_widget, text = tabName)

    viewText = view.text

    xlo = ylo = '0.0'
    xhi = yhi = '1.0'
    with suppress(Exception): xlo, xhi = view._hbar.get()
    with suppress(Exception): ylo, yhi = view._vbar.get()
    logging.debug("The scroll position was retrieved as: {}-{}, {}-{}".format(xlo, xhi, ylo, yhi))
    viewText['state'] = NORMAL
    viewText.set_content(blur(contents))
    viewText['state'] = DISABLED

    with suppress(Exception): view._hbar.set(xlo, xhi)
    if scrollToEnd:
        viewText.see(END)
    else:
        with suppress(Exception): view._vertical_scrollbar_update(ylo, yhi)

    clipboardEnforcer.syncText[syncKey] = contents

def addIfChanged(name, contents, building):
    ''' Adds to building if the contents have changed since last sent,
        or if they haven't been sent in the past 10 minutes. '''
    if (name not in sync.lastSentFiles
            or sync.lastSentFiles[name].contents != contents
            or sync.lastSentFiles[name].time     <= time() - 600):
        building[name] = contents

def sync():
    wb           = get_workbench()
    allFiles     = getAllFiles(wb)
    changedFiles = {}

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

    retractFiles = [f for f in sync.lastSentFiles if f != ':shell:' and f not in allFiles]

    if retractFiles:
        request['retract'] = retractFiles

    for var in 'lastVersion', 'lastUser', 'lastFile', 'prioritizeFile', 'requestUser', 'requestFile', 'lastShell':
        val = getattr(sync, var)
        if val is not None:
            request[var] = val

    try:
        r = requests.post('https://marksfam.com/class_sync/class_sync', json = request)

        try:
            response = r.json()
        except Exception:
            logging.exception('Failed to convert from json: ' + r.text)
            raise

        for f in changedFiles:
            sync.lastSentFiles[f] = SentFile(changedFiles[f], time())

        for f in retractFiles:
            sync.lastSentFiles.pop(f, None)  # Delete if it's there, ignore if it's not.

        sync.prioritizeFiles = None  # Ensure it's only ever declared as a priority once.

        sync.requestableFiles = response['files']
        updateMenu(wb)

        if 'version' in response:
            sync.lastVersion = response['version']
            sync.lastUser    = response['user']
            sync.lastFile    = response['file']
            syncHelper(wb, 'CodeMirrorView', 'Code Mirror - ' + requestablePairToName(sync.lastUser, sync.lastFile), response['body'], 'main')
            clipboardEnforcer.copyableText['allowed'] = ''.join(copyablePattern.findall(response['body']))

        if 'shellVersion' in response:
            sync.lastShell = response['shellVersion']
            sync.lastUser  = response['user']
            syncHelper(wb, 'ShellMirrorView', sync.lastUser + "'s Shell", response['shellBody'], 'shell', scrollToEnd = True)
    except Exception:
        logging.exception('Failure during sync.', exc_info = True)
    finally:
        if not get_workbench()._closing:
            logging.debug('Will kick off another sync in 5 seconds since there is no mention of the app closing as of: ' + ctime())
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
    except Exception:
        logging.exception('Clipboard enforcer got an error.', exc_info = True)
    finally:
        if not get_workbench()._closing:
            clipboardEnforcer.counter += 1
            if clipboardEnforcer.counter > 30:
                clipboardEnforcer.counter = 0
                logging.debug('Clipboard enforcer is still running since there is no mention of the app closing as of: ' + ctime())
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
    #wb.add_view(ImageView,       'Image View',   'se', visible_by_default = True)
    _default_root.after(7000, afterLoad)  # Give Thonny some time (7 seconds) to finish initializing