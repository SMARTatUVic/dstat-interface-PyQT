from PyQt5.QtCore import QObject, QRunnable, pyqtSlot, pyqtSignal

class WorkerSignals(QObject):
    msg = pyqtSignal(str)

class Worker(QRunnable):

    def __init__(self, fn):
        super(Worker, self).__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        self.fn(self.signals)

