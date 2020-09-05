import logging
import requests  # <<< This has to be listed as a prereq for this file.

from collections        import namedtuple
from getpass            import getuser
from re                 import DOTALL, IGNORECASE, compile as Regex
from thonny             import get_workbench
from thonny.codeview    import CodeView
from thonny.shell       import ShellView
from time               import time
from tkinter            import _default_root, Menu
from tkinter.messagebox import showinfo
from traceback          import format_exc
from threading          import Timer

copyablePattern = Regex(r'#\s*COPYABLE.*?#\s*END\s*COPYABLE', DOTALL | IGNORECASE)

# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
# 
# REQUIRED STEPS LEFT:
#  1 - Distribute the client side
#  2 - Test that it all works. All of it. Like actual syncing between clients stuff.
# 
# OPTIONAL STEPS LEFT:
#  1 - Add in line numbers, EnhancedTextFrame in the file tktextext.py offers this.
#  2 - Fix inconsistent font issues in CodeMirrorView.
#  3 - Fix fact that CodeMirrorView can be edited.
#  4 - Add an ability to deprioritize files.
#  5 - Add an ability to un-request files.
#  6 - Implement ShellMirrorView.
#  7 - Add in an assistant mirror view.
#  
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

class ShellMirrorView(ShellView):
    pass

    # ShellView has an _insert_text_directly method and also direct_insert...
    # It also has _editing_allowed...
    # 

    '''
    try:
        shellMirrorText = wb.get_view('ShellMirrorView').text
        showinfo('Got the text', 'Yes I did') 
        shellMirrorText.delete('1.0', 'end-1c')  # <<< This part causes errors.
        showinfo('Deleted', 'Yes I did') 
        shellMirrorText.insert('1.0', wb.get_view('ShellView').text.get('1.0', 'end-1c'))
        showinfo('Did the insert', 'And yet you do not appreciate')
    except BaseException as e:
        showinfo('Stack', format_exc()) 
    '''


class CodeMirrorView(CodeView):
    pass

    # When I tried setting an __init__ method it somehow didn't work... there was some Tk variable that it wanted but wasn't set.
    #def __init__(self, *args, **kwargs):
    #    super().__init__(self, *args, **kwargs)

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
        if newRequestable not in sync.requestableFiles:
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

    # Send everything that's never been sent before, or which has changed contents,
    # or which simply hasn't been sent in the past 10 minutes.
    for filename in allFiles:
        if (filename not in sync.lastSentFiles
                or sync.lastSentFiles[filename].contents != allFiles[filename]
                or sync.lastSentFiles[filename].time     >= time() + 600):
            changedFiles[filename] = allFiles[filename]

    clipboardEnforcer.copyableText['files'] = ''.join(allFiles.values())

    request = {'user': getuser()}

    if changedFiles:
        request['files'] = changedFiles

    for var in 'lastVersion', 'lastUser', 'lastFile', 'prioritizeFile', 'requestUser', 'requestFile':
        val = getattr(sync, var)
        if val is not None:
            request[var] = val
            if var == 'prioritizeFile':
                logging.info('Set prioritizeFile to ' + request[var] + ' in the request.')
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

        if 'version' in response:
            sync.lastVersion = response['version']
            sync.lastUser    = response['user']
            sync.lastFile    = response['file']

            codeMirrorText = wb.get_view('CodeMirrorView').text
            codeMirrorText.delete('1.0', 'end-1c')
            codeMirrorText.insert('1.0', response['body'])

            clipboardEnforcer.syncText = response['body']
            clipboardEnforcer.copyableText['allowed'] = ''.join(copyablePattern.findall(response['body']))
    except Exception:
        logging.exception('Failure during sync.', exc_info = True)
    finally:
        Timer(5, sync).start()

sync.requestableFiles = []
sync.lastSentFiles    = {}
sync.lastVersion      = None
sync.lastUser         = None
sync.lastFile         = None
sync.prioritizeFile   = None
sync.requestUser      = None
sync.requestFile      = None

def clipboardEnforcer():
    try:
        clipboardContents = _default_root.clipboard_get()
        if clipboardContents != clipboardEnforcer.previousClipboardContents:
            if clipboardContents in clipboardEnforcer.syncText and not any(clipboardContents in t for t in clipboardEnforcer.copyableText.values()):
                _default_root.clipboard_clear()
                _default_root.clipboard_append(clipboardEnforcer.previousClipboardContents)
                showinfo('Forbidden copy detected!', "You weren't allowed to copy that! Your clipboard has been rolled back!")
            else:
                clipboardEnforcer.previousClipboardContents = clipboardContents
    except:
        get_workbench().report_exception("Clipboard enforcer got an error.")
    finally:
        _default_root.after(200, clipboardEnforcer)

clipboardEnforcer.syncText     = ''
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
    logging.info('Loading classroom_sharing.py - will involve a 10 second wait.')
    wb = get_workbench()
    #wb.add_command(command_id="hello", menu_name="tools", command_label="Hello!", handler=sync)
    wb.add_view(CodeMirrorView,  'Code Mirror',  'ne', visible_by_default = False)
    #wb.add_view(ShellMirrorView,'Shell Mirror', 'se', visible_by_default = False)
    _default_root.after(10000, afterLoad)  # Give Thonny some time to finish initializing

# get_editor_notebook().get_current_editor().get_long_description() gives me the title of the full file path of whatever tab they have open.
