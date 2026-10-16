"""Keep a second launch from loading another speech model."""
import hashlib
from pathlib import Path
from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated=Signal()

    def __init__(self,home,parent=None):
        super().__init__(parent)
        home=Path(home).resolve()
        home.mkdir(parents=True,exist_ok=True)
        self.lock=QLockFile(str(home/'application.lock'))
        self.lock.setStaleLockTime(0)
        self.name='UniversalVoiceKR-'+hashlib.sha256(str(home).casefold().encode()).hexdigest()[:24]
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._activate)
        self.owned=False

    def acquire(self):
        if not self.lock.tryLock(0):
            socket=QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(1000):
                socket.disconnectFromServer()
            return False
        self.owned=True
        # Only the lock owner may clean a pipe left by a terminated process.
        QLocalServer.removeServer(self.name)
        self.server.listen(self.name)
        return True

    def _activate(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            socket.close();socket.deleteLater()
        self.activated.emit()

    def close(self):
        if self.owned:
            self.server.close()
            self.lock.unlock()
            self.owned=False
