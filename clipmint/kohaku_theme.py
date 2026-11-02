"""Option A: Kohaku Gothic Archive palette for the native PySide6 workspace.

The filigree lives in the Qt painter; these rules style interactive widgets,
not a flattened screenshot. Keep strong focus outlines and legible text.
"""

KOHaku_QSS = """
QMainWindow, QWidget#appRoot {background:#151016;color:#F4E7DE;
    font-family:"DejaVu Sans";font-size:12px;}
QLabel {color:#F4E7DE;background:transparent;}
QLabel#edition {color:#BFA5A0;font:11px "DejaVu Sans Mono";}
QLabel#kanaTag {color:#C8A8AB;font-family:"DotGothic16";font-size:13px;}
QLabel#mastLabel {color:#C8ABA6;font:11px Georgia;}
QLabel#systemReady {color:#D6ECA9;background:#211A21;
    border:1px solid #AD755A;border-radius:10px;padding:9px 12px;
    font:10px "DejaVu Sans Mono";}
QFrame#maidAlcove {border:0;background:transparent;}
QLabel#ledger {color:#E8AAA7;font:10px "DejaVu Sans Mono";}
QLabel#dossierName {font:italic 24px Georgia;color:#F2D5BB;}
QLabel#dossierJp {color:#F0C9AE;font-family:"DotGothic16";font-size:12px;}
QLabel#dossierRoman {color:#CBA5A1;font:italic 9px Georgia;}
QLabel#dossierEnglish {color:#E3C1B5;font:italic 10px Georgia;}
QWidget#archivePage {background:#1D1720;border:1px solid #764450;border-radius:5px;}
QLabel#eyebrow {color:#DF6F82;font:10px "DejaVu Sans Mono";}
QLabel#sectionTitle {color:#F2E1D1;font:24px Georgia;}
QLabel#archiveDate {color:#BFA9AB;font:10px "DejaVu Sans Mono";}
QTabBar {background:transparent;}
QTabBar::tab {background:transparent;color:#D1B7BC;border:0;
    border-bottom:1px solid #654451;padding:11px 16px;font:13px Georgia;}
QTabBar::tab:selected {color:#FFE8D8;background:#562637;
    border-bottom:2px solid #F08FA5;}
QTabBar::tab:hover {color:white;background:#49303C;}
QPushButton#addBin {color:#F57694;background:transparent;border:0;
    font-size:23px;padding:4px 8px;}
QLineEdit#archiveSearch {color:#F3E7E1;background:#241C27;
    border:1px solid #84505E;border-radius:18px;padding:10px 14px;
    font:11px "DejaVu Sans Mono";}
QLineEdit#archiveSearch:focus {border:1px solid #F8C49A;}
QLabel#filterLabel {color:#C9B4B4;font:10px "DejaVu Sans Mono";}
QComboBox {color:#F1E3DD;background:#2D222C;border:1px solid #855663;
    border-radius:3px;padding:7px 9px;font:11px "DejaVu Sans Mono";}
QComboBox QAbstractItemView {background:#2B202A;color:#F1E5DE;
    selection-background-color:#74354A;}
QLabel#counter {color:#D9BDBB;font:11px "DejaVu Sans Mono";}
QListWidget#clipHistory {background:#211922;color:#F5E9E4;
    border:1px solid #603B4C;border-radius:5px;outline:0;padding:2px;}
QListWidget#clipHistory::item {border:0;background:transparent;}
QListWidget#clipHistory::item:focus {border:1px solid #F1C69F;}
QFrame#previewPane {background:#201923;border:1px solid #744652;
    border-radius:6px;}
QLabel#previewTitle {font:italic 23px Georgia;color:#F3E3D5;}
QLabel#previewHeading {color:#E9909B;font-family:"DotGothic16";font-size:12px;}
QFrame#previewBorder {background:#15121A;border:1px solid #7E4E5B;border-radius:4px;}
QLabel#previewText {background:transparent;color:#F3E7E3;
    font:12px "DejaVu Sans Mono";padding:11px;}
QLabel#previewDimensions {color:#BEA5A9;font:11px "DejaVu Sans Mono";}
QLabel#previewName {color:#EFE0D7;font:15px Georgia;}
QLabel#previewSub {color:#BAA5AB;font:10px "DejaVu Sans Mono";}
QLabel#detailsHeading {color:#E77B8F;font:10px "DejaVu Sans Mono";}
QLabel#metaKey {color:#C5ABB1;font:11px "DejaVu Sans Mono";}
QLabel#metaValue {color:#F4E7DC;font:11px "DejaVu Sans Mono";}
QPushButton#previewCopy {background:#EBD2C4;color:#31202A;
    border:1px solid #F2DACB;border-radius:3px;
    padding:12px 5px;font:11px "DejaVu Sans Mono";}
QPushButton#previewAction {background:#382735;color:#F5E3DF;
    border:1px solid #905568;border-radius:3px;
    padding:12px 5px;font:11px "DejaVu Sans Mono";}
QPushButton#previewAction:hover, QPushButton#previewCopy:hover {
    background:#8E455C;color:white;}
QFrame#dock {background:#1E1721;border:1px solid #764757;border-radius:6px;}
QLabel#dockHeading {color:#C8ADA7;font:10px "DejaVu Sans Mono";}
QPushButton#nav {background:transparent;border:0;
    border-left:3px solid transparent;border-radius:3px;
    color:#E1CDC3;text-align:left;padding:9px 10px;
    font:11px "DejaVu Sans";}
QPushButton#nav:checked {background:#5C283C;
    border-left:3px solid #F590A7;color:#FFF3E4;}
QPushButton#nav:hover {background:#492D3A;}
QPushButton#nav:focus {border-left:3px solid #F4CE9C;}
QLabel#dockStamp {color:#CB8997;font-family:"DotGothic16";font-size:10px;}
QFrame#footer {background:transparent;border-top:1px solid #7D4957;}
QLabel#footerStatus {color:#C8B1B7;font:10px "DejaVu Sans Mono";}
QLabel#footerNote {color:#EBA6AD;font:10px "DejaVu Sans Mono";}
QPushButton#record {background:#A62443;color:#FFF0E8;border:1px solid #BB526E;}
QPushButton#screenshot {background:#E4CEC4;color:#2A1720;border:1px solid #F7E2D7;}
QPushButton:focus,QToolButton:focus,QLineEdit:focus,QComboBox:focus,
QListWidget:focus,QCheckBox:focus {border:1px solid #F4D0A6;}
QScrollBar:vertical {background:#211921;width:10px;margin:2px;}
QScrollBar::handle:vertical {background:#704153;border-radius:4px;min-height:25px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QMenu {background:#271C29;color:#F3E0D8;border:1px solid #87586A;}
QMenu::item:selected {background:#633047;}
QGroupBox {border:1px solid #7A4A59;border-radius:5px;margin-top:10px;
    padding:11px;color:#F2D7C8;}
QGroupBox::title {subcontrol-origin:margin;left:12px;}
QCheckBox {color:#E8D6CF;spacing:6px;}
QPushButton {border:1px solid #875468;border-radius:4px;
    background:#3A2937;color:#EEDDDA;padding:7px 11px;}
QPushButton:hover {background:#6C354A;}
QPushButton:disabled {color:#88777C;background:#28222B;}
QLineEdit {color:#F4E6DE;background:#2C202A;border:1px solid #845363;
    padding:7px;border-radius:4px;}
QListWidget {color:#F2E5E1;background:#251D28;border:1px solid #754654;
    border-radius:4px;}
QListWidget::item:selected {background:#6B364B;}
"""
