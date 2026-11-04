"""Kohaku Gothic Archive: native Qt theme tuned to the approved 1507x1044 UI.

The references use old-world book typography, gold hairlines and lacquered
burgundy surfaces. Actual widgets stay interactive, keyboard focus remains
visible and the approved illustration is never repainted or cropped.
"""
from __future__ import annotations

# The Cormorant Garamond OFL display font is loaded offline by branding.py.
# Georgia is the deliberate fallback for source checkouts without bundled fonts.
GOTHIC_SERIF = "Cormorant Garamond"
INK = "#17121A"
LACQUER = "#241823"
ROSE = "#C07085"
GOLD = "#D7A17C"
IVORY = "#F5E6D8"

KOHaku_QSS = """
QMainWindow, QWidget#appRoot {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #201923,stop:0.22 #151018,stop:0.83 #17111A,stop:1 #100D14);
    color:#F5E7DF; font-family:"Georgia"; font-size:13px;
}
QLabel {color:#F5E7DF;background:transparent;font-family:"Georgia";}
QLabel#edition {color:#CEB1A8;font:12px "DejaVu Sans Mono";}
QLabel#kanaTag {color:#CBA5A9;font-family:"DotGothic16";font-size:14px;}
QLabel#mastLabel {color:#CDB6B3;font:12px "Georgia";}
QLabel#systemReady {
    color:#D2E6A7;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #251A24,stop:1 #151019);
    border:1px solid #C48C6B; border-radius:15px;
    padding:12px 18px;
    font:11px "DejaVu Sans Mono";
}
QFrame#maidAlcove {background:#1A101A;border:1px solid #8E5962;border-radius:7px;}
QFrame#maidDossier {background:transparent;border:0;}
QLabel#ledger {color:#D9979C;font:11px "DejaVu Sans Mono";}
QLabel#dossierName {color:#FFE1BE;font:italic 29px "Cormorant Garamond";}
QLabel#dossierJp {color:#F0C8AC;font-family:"DotGothic16";font-size:12px;}
QLabel#dossierRoman {color:#D8ADA6;font:italic 12px "Cormorant Garamond";}
QLabel#dossierEnglish {color:#EBD4CB;font:italic 13px "Cormorant Garamond";}
QWidget#archivePage {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #221920,stop:0.55 #19131C,stop:1 #1D1620);
    border:1px solid #89545D; border-radius:9px;
}
QFrame#archiveHead {background:transparent;border:0;}
QLabel#eyebrow {color:#E08398;font:11px "DejaVu Sans Mono";}
QLabel#sectionTitle {color:#F7E0C9;font:28px "Cormorant Garamond";}
QLabel#archiveDate {color:#D0B4B4;font:11px "DejaVu Sans Mono";}
QTabBar {background:transparent;border:0;}
QTabBar::tab {
    background:transparent;color:#D3BBC0;
    border:0;border-bottom:1px solid #76545B;
    padding:12px 23px;font:16px "Cormorant Garamond";
}
QTabBar::tab:selected {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #633040,stop:1 #41202F);
    color:#FFF0DF;border:1px solid #965065;
    border-bottom:2px solid #E7899F;border-top-left-radius:5px;border-top-right-radius:5px;
}
QTabBar::tab:hover:!selected {background:#392734;color:#FFF1E3;}
QPushButton#addBin {color:#FF7998;background:transparent;border:0;font:25px "Georgia";padding:2px 8px;}
QFrame#archiveSearchCapsule {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2A202C,stop:1 #231B27);
    border:1px solid #9C6274;border-radius:20px;min-height:37px;
}
QLabel#archiveSearchGlyph {color:#E5C4B5;font:20px "Georgia";}
QLineEdit#archiveSearch {
    color:#F8E9DD;background:transparent;border:0;border-radius:0;
    padding:7px 0;selection-background-color:#74405B;font:13px "Georgia";
}
QLineEdit#archiveSearch:focus {border:0;color:#FFECDF;}
QLabel#filterLabel {color:#D1B6BC;font:11px "DejaVu Sans Mono";}
QComboBox {
    color:#F5E7DE;background:#2B212D;border:1px solid #8B5664;
    border-radius:4px;padding:8px 11px;font:11px "DejaVu Sans Mono";
}
QComboBox:focus {border:1px solid #F3C19F;}
QComboBox QAbstractItemView {
    background:#2A1E2A;color:#F3E2D9;selection-background-color:#774058;
}
QLabel#counter {color:#E4C8C8;font:11px "DejaVu Sans Mono";}
QListWidget#clipHistory {
    background:transparent;color:#F5E7DD;border:0;
    outline:0;padding:1px;
}
QListWidget#clipHistory::item {border:0;background:transparent;}
QListWidget#clipHistory::item:focus {border:1px solid #EDB38E;}
QFrame#previewPane {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #241B24,stop:1 #1B1520);
    border:1px solid #865361;border-radius:9px;
}
QLabel#previewTitle {color:#F8E3D3;font:italic 26px "Cormorant Garamond";}
QLabel#previewHeading {color:#E18D9D;font:13px "Georgia";}
QFrame#previewBorder {
    background:#17131C;border:1px solid #805665;border-radius:7px;
}
QLabel#previewText {background:transparent;color:#F3E6E0;font:12px "DejaVu Sans Mono";padding:11px;}
QLabel#previewDimensions {color:#D3B1BA;font:11px "DejaVu Sans Mono";}
QLabel#previewName {color:#F4DED0;font:20px "Cormorant Garamond";}
QLabel#previewSub {color:#C9ADB1;font:11px "DejaVu Sans Mono";}
QLabel#detailsHeading {color:#E68D9C;font:12px "DejaVu Sans Mono";}
QLabel#metaKey {color:#C3AAB0;font:11px "Georgia";}
QLabel#metaValue {color:#F1E2DD;font:11px "DejaVu Sans Mono";}
QPushButton#previewCopy {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #F0DECF,stop:1 #D4B6AC);
    color:#2F1D26;border:1px solid #F6E3D6;border-radius:4px;
    padding:11px 7px;font:13px "Cormorant Garamond";
}
QPushButton#previewAction {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4B2D3C,stop:1 #301F2F);
    color:#F7E6DD;border:1px solid #995C6F;border-radius:4px;
    padding:11px 6px;font:13px "Cormorant Garamond";
}
QPushButton#previewAction:hover {background:#704052;}
QPushButton#previewCopy:hover {background:#F8E9DF;}
QFrame#dock {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #221923,stop:1 #17121B);
    border:1px solid #865562;border-radius:9px;
}
QLabel#dockHeading {color:#D5B4B4;font:11px "Cormorant Garamond";}
QPushButton#nav {
    background:transparent;color:#EBD5C8;text-align:left;
    border:0;border-left:3px solid transparent;border-radius:5px;
    padding:9px 9px;font:14px "Cormorant Garamond";
}
QPushButton#nav:hover {background:#49303D;}
QPushButton#nav:checked {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6A3047,stop:1 #452333);
    color:#FFF0E3;border-left:3px solid #EC8DA2;
}
QPushButton#nav:focus {border-left:3px solid #E9BD91;}
QLabel#dockStamp {color:#D18CA2;font:11px "Cormorant Garamond";}
QFrame#footer {background:transparent;border-top:1px solid #8C515B;}
QLabel#footerStatus {color:#E6B6BB;font:11px "Cormorant Garamond";}
QLabel#footerNote {color:#DB9CA9;font:10px "DejaVu Sans Mono";}
QPushButton:focus, QToolButton:focus, QLineEdit:focus,
QComboBox:focus, QListWidget:focus, QCheckBox:focus {
    border:1px solid #F1BA8B;
}
QPushButton:disabled {color:#8E7780;background:#29212A;}
QPushButton {background:#412C37;color:#F5E3DA;border:1px solid #8A5363;border-radius:5px;padding:8px 11px;}
QPushButton:hover {background:#714252;}
QLineEdit {
    background:#2A202B;color:#F5E5DC;border:1px solid #885464;
    padding:8px;border-radius:5px;
}
QListWidget {background:#241C28;color:#F2E3DC;border:1px solid #875665;border-radius:5px;}
QListWidget::item:selected {background:#703C50;}
QMenu {background:#261A27;color:#F8E6DF;border:1px solid #A5667C;}
QMenu::item:selected {background:#61354C;}
QCheckBox {color:#F2DED6;}
QGroupBox {color:#F4D8C8;border:1px solid #865465;border-radius:5px;margin-top:10px;padding:10px;}
QGroupBox::title {subcontrol-origin:margin;left:12px;}
QDialog {
    background:#1A131D;color:#F6E4D9;
}
QPlainTextEdit, QTextEdit {
    background:#231925;color:#F4E4DD;
    border:1px solid #855265;border-radius:6px;
    selection-background-color:#6F394F;
    font:12px "DejaVu Sans Mono";padding:8px;
}
QPlainTextEdit:focus, QTextEdit:focus {border:1px solid #E4A98F;}
QListWidget::item:hover {background:#4A2B3B;}
QScrollBar:vertical {background:#1D1520;width:11px;margin:2px;}
QScrollBar::handle:vertical {background:#754257;border:1px solid #9B6276;border-radius:5px;min-height:28px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QComboBox#tagFilter {
    background:#291D29;color:#F3D6CA;border:1px solid #865365;
    border-radius:5px;padding:5px 7px;font:12px "Cormorant Garamond";
}
QCheckBox#favoriteFilter {
    color:#EBC3C6;background:transparent;font:13px "Cormorant Garamond";
    spacing:4px;
}
QCheckBox#favoriteFilter::indicator {
    width:14px;height:14px;border:1px solid #B6768C;
    background:#281C2A;border-radius:3px;
}
QCheckBox#favoriteFilter::indicator:checked {
    background:#B95170;border:1px solid #F1B9A4;
}
QPushButton#organizerAction {
    color:#F8E3D5;background:#412734;border:1px solid #945769;
    border-radius:5px;padding:6px 7px;font:13px "Cormorant Garamond";
}
QPushButton#organizerAction:hover {background:#66384C;}
QPushButton#organizerAction:disabled {
    color:#8F7783;background:#2A202A;border:1px solid #5F4651;
}

/* Capture archive: coordinated with the Crimson/Kohaku navigation and ledger. */
QWidget#captureLibraryPage {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #281B27,stop:1 #1B131C);
    border:1px solid #865563;border-radius:9px;
}
QLabel#captureEyebrow {
    background:transparent;color:#DE91A3;
    font:11px "DejaVu Sans Mono";
}
QLabel#captureHint {
    background:transparent;color:#D7B8BD;
    font:12px "Georgia";
}
QLabel#captureFilename {
    background:transparent;color:#FFE4D6;
    font:20px "Cormorant Garamond";
}
QLabel#captureDetails {
    background:transparent;color:#D4B0B9;
    font:11px "DejaVu Sans Mono";
}
QListWidget#screenshotGallery {
    background:#1D1520;color:#F5E5DC;
    border:1px solid #805064;border-radius:8px;
    padding:8px;outline:0;
}
QListWidget#screenshotGallery::item {
    background:#31212E;color:#F4E2D8;
    border:1px solid #674152;border-radius:7px;
    padding:5px;margin:3px;
    font:12px "Cormorant Garamond";
}
QListWidget#screenshotGallery::item:hover {
    background:#493044;border:1px solid #AC7185;
}
QListWidget#screenshotGallery::item:selected {
    background:#66364B;border:2px solid #E8A0AE;
    color:#FFF3E7;
}
QListWidget#screenshotGallery::item:focus {border:2px solid #F1C59D;}
QListWidget#recordingLibrary {
    background:#1D1520;color:#F4E3D9;
    border:1px solid #805064;border-radius:7px;padding:8px;
    font:13px "DejaVu Sans Mono";
}
QFrame#capturePreviewPane {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #2E202E,stop:1 #1B141F);
    border:1px solid #A06877;border-radius:8px;
}
QLabel#screenshotLargePreview {
    background:#151019;border:1px solid #6E4658;border-radius:6px;
}
QPushButton#captureAction {
    color:#F7E6D7;background:#4C2D40;
    border:1px solid #A36F7D;border-radius:5px;
    padding:8px 10px;font:13px "Cormorant Garamond";
}
QPushButton#captureAction:hover {background:#73445B;}
QPushButton#captureAction:focus {border:2px solid #F1C59D;}
"""
