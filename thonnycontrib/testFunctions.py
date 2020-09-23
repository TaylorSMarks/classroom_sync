from classroom_sharing import addIfChanged, blur, getAllFiles, SentFile, sync, updateMenu
from time              import time
from tkinter           import Menu
from unittest          import main as runTests, TestCase
from unittest.mock     import MagicMock

# To run this and get a coverage report on Windows, run this from PowerShell
# (obviously you have to be in the correct directory and have run pip install coverage already...)
# coverage run --branch testFunctions.py; coverage html; Start htmlcov\index.html

class TestFunctions(TestCase):
    def testBlur(self):
        self.assertEqual(blur('''firstLine()
            secondLine() #blur
            thirdLine()'''), '''firstLine()
            __________() 
            thirdLine()''')

    def testAddIfChanged(self):
        sync.lastSentFiles = {
            'f0': SentFile('c0', time()),
            'f1': SentFile('c1', time() - 900),
            'f2': SentFile('c2', time()),
            'f3': SentFile('c3', time() - 900)
        }

        filesToTry = {
            'f0': 'c8',  # old name, new contents, just sent
            'f1': 'c9',  # old name, new contents, sent 900 seconds ago
            'f2': 'c2',  # old name, old contents, just sent
            'f3': 'c3',  # old name, old contents, sent 900 seconds ago
            'f4': 'ca',  # new name, new contents, n/a previously sent
            'f5': 'c2'   # new name, old contents, n/a previously sent
        }

        building = {}
        for name in filesToTry:
            addIfChanged(name, filesToTry[name], building)

        self.assertEqual(building, {
            # All of them except old name, old contents, just sent (f2):
            'f0': 'c8',
            'f1': 'c9',
            'f3': 'c3',
            'f4': 'ca',
            'f5': 'c2'
        })

    def testUpdateMenu(self):
        wbMock                     = MagicMock()
        wbMock.get_menu            = MagicMock(return_value = Menu())
        notebook                   = MagicMock()
        wbMock.get_editor_notebook = MagicMock(return_value = notebook)
        editorMock1                = MagicMock()
        editorMock1.get_title      = MagicMock(return_value = 'f0')
        editorMock1.is_modified    = MagicMock(return_value = False)
        editorMock2                = MagicMock()
        editorMock2.get_title      = MagicMock(return_value = 'f1*')
        editorMock2.is_modified    = MagicMock(return_value = True)
        editorMock3                = MagicMock()
        editorMock3.get_title      = MagicMock(return_value = 'f0')
        editorMock3.is_modified    = MagicMock(return_value = False)
        notebook.get_all_editors   = MagicMock(return_value = [editorMock1, editorMock2, editorMock3])
        self.assertEqual(getAllFiles(wbMock).keys(), {'f0', 'f0-1', 'f1'})
        updateMenu(wbMock)

        sync.requestableFiles = [['taylor', 'f0'], ['taylor', 'f1']]
        updateMenu(wbMock)
        self.assertEqual(    updateMenu.oldRequestable, sync.requestableFiles)
        self.assertEqual(set(updateMenu.oldSharable),   {'f0', 'f0-1', 'f1'})

        notebook.get_all_editors = MagicMock(return_value = [editorMock1])
        sync.requestableFiles    = [['taylor', 'f1'], ['taylor', 'f2']]
        updateMenu(wbMock)
        self.assertEqual(updateMenu.oldRequestable,  sync.requestableFiles)
        self.assertEqual(updateMenu.oldSharable,     ['f0'])
        self.assertEqual(getAllFiles(wbMock).keys(), {'f0'})

        # Run one of the view commands just to ensure those are considered covered.
        updateMenu.viewMenu.invoke(0)
        self.assertEqual(sync.requestUser, 'taylor')
        self.assertEqual(sync.requestFile, 'f1')

        updateMenu.showMenu.invoke(0)
        self.assertEqual(sync.prioritizeFile, 'f0')

runTests()