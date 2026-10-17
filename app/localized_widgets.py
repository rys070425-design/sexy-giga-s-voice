"""Own UI controls retain source labels for immediate language changes.

Only chrome uses these classes. Subtitle labels and editable values stay native.
"""
from PySide6 import QtWidgets as W
from PySide6.QtCore import Qt
from ui_i18n import translate,register

SOURCE_ROLE=int(Qt.UserRole)+87

class UiProperties:
    def _ui_set(self,method,source):
        if not hasattr(self,'_ui_sources'):self._ui_sources={};register(self)
        self._ui_sources[method]=str(source)
        getattr(super(UiProperties,self),method)(translate(source))
    def setToolTip(self,text):self._ui_set('setToolTip',text)
    def setWindowTitle(self,text):self._ui_set('setWindowTitle',text)
    def retranslate_ui(self):
        for method,source in getattr(self,'_ui_sources',{}).items():
            getattr(super(UiProperties,self),method)(translate(source))

def text_control(base,method):
    class Control(UiProperties,base):
        def __init__(self,*args,**kwargs):
            args=list(args);source=None
            if args and isinstance(args[0],str):source=args[0];args[0]=''
            key='title' if method=='setTitle' else 'text'
            if key in kwargs:source=kwargs.pop(key)
            super().__init__(*args,**kwargs)
            if source is not None:self._ui_set(method,source)
    def setter(self,text):self._ui_set(method,text)
    setattr(Control,method,setter)
    return Control

QLabel=text_control(W.QLabel,'setText')
QPushButton=text_control(W.QPushButton,'setText')
QCheckBox=text_control(W.QCheckBox,'setText')
QGroupBox=text_control(W.QGroupBox,'setTitle')

class QLineEdit(UiProperties,W.QLineEdit):
    def setPlaceholderText(self,text):self._ui_set('setPlaceholderText',text)

class QTextEdit(UiProperties,W.QTextEdit):
    def setPlaceholderText(self,text):self._ui_set('setPlaceholderText',text)

class QPlainTextEdit(UiProperties,W.QPlainTextEdit):
    def setPlaceholderText(self,text):self._ui_set('setPlaceholderText',text)

class QDialog(UiProperties,W.QDialog):pass

class QStatusBar(UiProperties,W.QStatusBar):
    def showMessage(self,text,timeout=0):
        self._last_ui_message=str(text);register(self)
        super().showMessage(translate(text),timeout)
    def retranslate_ui(self):
        super().retranslate_ui()
        if hasattr(self,'_last_ui_message'):super().showMessage(translate(self._last_ui_message))

class QMainWindow(UiProperties,W.QMainWindow):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setStatusBar(QStatusBar(self))

class QComboBox(UiProperties,W.QComboBox):
    def addItem(self,text,userData=None):
        super().addItem(translate(text),userData)
        self.setItemData(self.count()-1,str(text),SOURCE_ROLE);register(self)
    def addItems(self,texts):
        for text in texts:self.addItem(text)
    def insertItem(self,index,text,userData=None):
        super().insertItem(index,translate(text),userData)
        self.setItemData(index,str(text),SOURCE_ROLE);register(self)
    def setItemText(self,index,text):
        self.setItemData(index,str(text),SOURCE_ROLE)
        super().setItemText(index,translate(text));register(self)
    def retranslate_ui(self):
        super().retranslate_ui()
        blocked=self.blockSignals(True)
        try:
            for index in range(self.count()):
                text=self.itemData(index,SOURCE_ROLE)
                if text is not None:super().setItemText(index,translate(text))
        finally:self.blockSignals(blocked)

class QListWidget(UiProperties,W.QListWidget):
    def addItem(self,item):
        if isinstance(item,str):
            source=item;item=W.QListWidgetItem(translate(source));item.setData(SOURCE_ROLE,source)
        super().addItem(item);register(self)
    def addItems(self,items):
        for item in items:self.addItem(item)
    def retranslate_ui(self):
        super().retranslate_ui()
        for index in range(self.count()):
            item=self.item(index);source=item.data(SOURCE_ROLE)
            if source is not None:item.setText(translate(source))

class QTabWidget(UiProperties,W.QTabWidget):
    def addTab(self,widget,label):
        widget.setProperty('ui_tab_source',str(label));register(self)
        return super().addTab(widget,translate(label))
    def insertTab(self,index,widget,label):
        widget.setProperty('ui_tab_source',str(label));register(self)
        return super().insertTab(index,widget,translate(label))
    def retranslate_ui(self):
        super().retranslate_ui()
        for index in range(self.count()):
            label=self.widget(index).property('ui_tab_source')
            if label is not None:super().setTabText(index,translate(label))

class QFormLayout(W.QFormLayout):
    def addRow(self,*args):
        if len(args)==2 and isinstance(args[0],str):
            label=QLabel(args[0]);label.setWordWrap(True)
            if isinstance(args[1],W.QWidget):label.setBuddy(args[1])
            return super().addRow(label,args[1])
        return super().addRow(*args)

class QMessageBox(W.QMessageBox):pass
for name in ('information','warning','critical','question'):
    def call(parent,title,text,*args,_name=name,**kwargs):
        return getattr(W.QMessageBox,_name)(parent,translate(title),translate(text),*args,**kwargs)
    setattr(QMessageBox,name,staticmethod(call))

class QFileDialog(W.QFileDialog):pass
for name in ('getOpenFileName','getSaveFileName','getExistingDirectory'):
    def call(parent,title,*args,_name=name,**kwargs):
        return getattr(W.QFileDialog,_name)(parent,translate(title),*args,**kwargs)
    setattr(QFileDialog,name,staticmethod(call))

class QInputDialog(W.QInputDialog):pass
for name in ('getText','getMultiLineText','getInt','getItem'):
    def call(parent,title,label,*args,_name=name,**kwargs):
        return getattr(W.QInputDialog,_name)(parent,translate(title),translate(label),*args,**kwargs)
    setattr(QInputDialog,name,staticmethod(call))
