"""Crimson Archive: native PySide6 implementation of the approved visual layout.

Composition and colours derive from the user's v2 HTML prototype.
All buttons are real Qt controls, using ClipMint's existing clipboard/capture
methods; no browser view, JavaScript renderer, demo data, or network calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygon, QLinearGradient, QBrush, QPainterPath, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QSizePolicy, QStackedWidget, QStyledItemDelegate, QStyle,
    QTabBar, QToolButton, QVBoxLayout, QWidget, QMenu, QCheckBox,
)

from .manga import CrimsonMaidPortrait
from .kohaku_card import KohakuCardFrame
from .kohaku_theme import KOHaku_QSS
from .crimson_widgets import (
    ROSE, LIME, PORCELAIN, MUTED, GothicSearchCapsule, GothicDivider,
    CrimsonFooterButton, CrimsonFooterArrow, CrimsonClipDelegate, label_type,
)

CRIMSON_QSS = """
QMainWindow, QWidget#appRoot {background:#0B090F;color:#F4EEEB;font-family:"DejaVu Sans";font-size:12px;}
QLabel {color:#F4EEEB;background:transparent;}
QLabel#edition {color:#BCA5AD;font:10px "DejaVu Sans Mono";}
QLabel#kanaTag {color:#D34D6A;font-family:"DotGothic16";font-size:13px;}
QLabel#mastLabel {color:#BBAAB3;font:10px "DejaVu Sans Mono";}
QLabel#systemReady {color:#C9F473;background:#20241B;padding:10px 12px;font:10px "DejaVu Sans Mono";}
QFrame#maidAlcove {background:#20141C;border-top:1px solid #995061;border-left:1px solid #503140;}
QLabel#ledger {color:#F0809A;font:10px "DejaVu Sans Mono";letter-spacing:1px;}
QFrame#maidDossier {background:#241821;border-top:1px solid #B95B70;}
QLabel#dossierName {font:italic 20px Georgia;color:#F4EEEB;}
QLabel#dossierSub {color:#BFAAB4;font:10px "DejaVu Sans Mono";}
QLabel#dossierJp {color:#D899A9;font-family:"DotGothic16";font-size:11px;}
QLabel#dossierStatus {color:#C9F473;font:10px "DejaVu Sans Mono";border-top:1px solid #784351;padding-top:5px;}
QWidget#archivePage {background:#111017;}
QFrame#archiveHead {background:transparent;}
QLabel#eyebrow {color:#FF6780;font:10px "DejaVu Sans Mono";}
QLabel#sectionTitle {color:#F4EEEB;font-size:20px;font-weight:600;}
QLabel#archiveDate {color:#A29DA6;font:10px "DejaVu Sans Mono";}
QTabBar {background:transparent;}
QTabBar::tab {background:transparent;color:#C5B9BF;border:0;border-bottom:1px solid #58404A;padding:12px 17px;font-size:12px;}
QTabBar::tab:selected {color:#F4EEEB;background:#35212B;border-bottom:3px solid #FF6780;}
QTabBar::tab:hover {color:#FFFFFF;background:#30212A;}
QPushButton#addBin {color:#FF6780;background:transparent;border:0;font-size:22px;padding:3px 9px;}
QLineEdit#archiveSearch {color:#F4EEEB;background:#221A24;border:0;border-bottom:1px solid #5B3B49;padding:12px 14px;font:12px "DejaVu Sans Mono";}
QLineEdit#archiveSearch:focus {border-bottom:2px solid #C9F473;}
QLabel#filterLabel {color:#BAA9B1;font:10px "DejaVu Sans Mono";}
QComboBox {color:#F4EEEB;background:#211820;border:1px solid #4A343D;padding:7px 8px;font:11px "DejaVu Sans Mono";}
QComboBox QAbstractItemView {background:#251924;color:#F4EEEB;selection-background-color:#54303D;}
QLabel#counter {color:#D6C6CC;font:11px "DejaVu Sans Mono";}
QListWidget#clipHistory {background:#111017;color:#F4EEEB;border:0;outline:0;padding:0;}
QListWidget#clipHistory::item {border:0;background:transparent;}
QListWidget#clipHistory::item:focus {border:1px solid #C9F473;}
QFrame#previewPane {background:#17131C;border-left:1px solid #5D3947;}
QLabel#previewTitle {font-size:18px;color:#F4EEEB;}
QLabel#previewHeading {color:#FF6780;font-family:"DotGothic16";font-size:12px;}
QFrame#previewBorder {background:#0F0C12;border:1px solid #533743;}
QLabel#previewText {background:transparent;color:#EADBE0;font:12px "DejaVu Sans Mono";padding:10px;}
QLabel#previewDimensions {color:#AFA1A7;font:11px "DejaVu Sans Mono";}
QLabel#previewName {color:#F4EEEB;font-size:14px;font-weight:600;}
QLabel#previewSub {color:#A99BA2;font:10px "DejaVu Sans Mono";}
QLabel#detailsHeading {color:#FF6780;font:10px "DejaVu Sans Mono";}
QLabel#metaKey {color:#B9A6AC;font:11px "DejaVu Sans Mono";}
QLabel#metaValue {color:#F0E4E7;font:11px "DejaVu Sans Mono";}
QPushButton#previewCopy {background:#E3D6D7;color:#281822;border:1px solid #E3D6D7;padding:10px 5px;font:11px "DejaVu Sans Mono";}
QPushButton#previewAction {background:#392633;color:#F4EEEB;border:1px solid #6C4652;padding:10px 5px;font:11px "DejaVu Sans Mono";}
QPushButton#previewAction:hover, QPushButton#previewCopy:hover {background:#7B4859;color:#FFF;}
QFrame#dock {background:#121016;border-left:1px solid #4C323A;}
QLabel#dockHeading {color:#9F949C;font:9px "DejaVu Sans Mono";}
QPushButton#nav {background:transparent;border:0;border-left:2px solid transparent;color:#CAB9C1;text-align:left;padding:9px 8px;font-size:12px;}
QPushButton#nav:checked {background:#40202C;border-left:3px solid #FF6780;color:#FFFFFF;}
QPushButton#nav:hover {background:#30212A;}
QPushButton#nav:focus {border-left:3px solid #C9F473;}
QLabel#dockStamp {color:#A15872;font-family:"DotGothic16";font-size:11px;}
QFrame#footer {background:transparent;border-top:1px solid #673648;}
QLabel#footerStatus {color:#B2A6AC;font:10px "DejaVu Sans Mono";}
QLabel#footerNote {color:#DD8795;font:10px "DejaVu Sans Mono";}
QPushButton#record {background:#A62443;color:#F4EEEB;border:1px solid #B6304C;padding:12px 18px;text-align:left;font-size:13px;font-weight:600;}
QPushButton#screenshot {background:#DFD3D2;color:#25151C;border:1px solid #EEE8E7;padding:12px 18px;text-align:left;font-size:13px;font-weight:600;}
QToolButton#recordArrow {background:#A62443;color:#F4EEEB;border:1px solid #B6304C;padding:12px;}
QToolButton#shotArrow {background:#DFD3D2;color:#25151C;border:1px solid #EEE8E7;padding:12px;}
QToolButton::menu-indicator {image:none;}
QPushButton#record:hover, QToolButton#recordArrow:hover {background:#C02C50;}
QPushButton#screenshot:hover, QToolButton#shotArrow:hover {background:#F1E4E1;}
QPushButton:focus, QToolButton:focus, QComboBox:focus {border:1px solid #C9F473;}
/* Footer plaque size is set by Qt; do not override it with a legacy QSS min-height. */
"""


def relative_time(created_at: str) -> str:
    """Datetime-aware elapsed time, without implying the clip's origin."""
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = max(0, int((datetime.now(timezone.utc) - created).total_seconds()))
    except (ValueError, TypeError, AttributeError):
        return "—"
    if delta < 60:
        return "now"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def make_label(text: str, name: str, parent=None) -> QLabel:
    label=QLabel(text,parent)
    label.setObjectName(name)
    return label


def build_crimson_ui(w, image_preview_class):
    """Recompose the window without replacing existing data or capture methods."""
    w.resize(1300, 870)
    w.setMinimumSize(850, 600)
    w.setStyleSheet(CRIMSON_QSS + '\n' + KOHaku_QSS)
    shell=QWidget()
    shell.setObjectName("appRoot")
    root=QVBoxLayout(shell)
    root.setContentsMargins(15,12,15,11)
    root.setSpacing(10)

    # Masthead
    mast=QHBoxLayout()
    mast.setSpacing(15)
    w.wordmark=w.wordmark.__class__(w.brand_family)
    w.wordmark.display_font.setPixelSize(53)
    w.wordmark.setFixedSize(w.wordmark.sizeHint())
    mast.addWidget(w.wordmark)
    w.kana_tag=make_label("クリップミント","kanaTag")
    w.kana_tag.setAccessibleName("ClipMint, written in Japanese Katakana")
    mast.addWidget(w.kana_tag)
    mast.addWidget(make_label("/ 04","edition"))
    mast.addStretch(1)
    mast.addWidget(make_label("●   SYSTEM READY   ◇","systemReady"))
    root.addLayout(mast)
    top_rule=GothicDivider()
    root.addWidget(top_rule)

    # Four columns: portrait, real working pages, preview, navigation.
    workspace=QHBoxLayout()
    workspace.setContentsMargins(0,0,0,0)
    workspace.setSpacing(12)

    w.manga_dock=KohakuCardFrame()
    w.manga_dock.setFixedWidth(354)
    alcove=QVBoxLayout(w.manga_dock)
    alcove.setContentsMargins(16,15,16,14)
    alcove.setSpacing(4)
    alcove.addWidget(make_label("FILE / 001   CHARACTER","ledger"))
    w.manga_mascot=CrimsonMaidPortrait(w.manga_dock)
    w.manga_mascot.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    alcove.addWidget(w.manga_mascot,1)
    # Character identity and the user's Ephemeral Catch are part of the card,
    # not a separate cyber-dossier footer. Text remains selectable/accessible.
    dossier=QFrame()
    dossier.setObjectName("maidDossier")
    dossier.setMinimumHeight(154)
    dl=QVBoxLayout(dossier)
    dl.setContentsMargins(6,4,6,4)
    dl.setSpacing(5)
    w.maid_caption=make_label("Kohaku  琥珀","dossierName")
    w.maid_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.maid_caption.setAccessibleName("Kohaku, 琥珀")
    dl.addWidget(w.maid_caption)
    jp=make_label("泡沫の如き刹那の思念、悉く我が掌底に封ず。","dossierJp")
    jp.setWordWrap(True)
    jp.setAlignment(Qt.AlignmentFlag.AlignCenter)
    jp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    dl.addWidget(jp)
    roman=make_label(
        "Utakata no gotoki setsuna no shinen, kotogotoku waga shōtei ni fūzu.",
        "dossierRoman")
    roman.setWordWrap(True)
    roman.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dl.addWidget(roman)
    english=make_label(
        "Transient thoughts that mimic foam upon the water—"
        "every last one is sealed within the hollow of my palm.",
        "dossierEnglish")
    english.setWordWrap(True)
    english.setAlignment(Qt.AlignmentFlag.AlignCenter)
    english.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    dl.addWidget(english)
    w.kohaku_japanese=jp
    w.kohaku_roman=roman
    w.kohaku_english=english
    alcove.addWidget(dossier)
    if w.manga_dock.has_card_art:
        # The supplied card already contains its own frame, character, title,
        # Japanese verse and translation. Do not paint or overlay them again.
        # Keep semantic labels attached for accessibility without rendering
        # duplicate copy over the original print artwork.
        alcove.setContentsMargins(0, 0, 0, 0)
        for element in (w.manga_mascot, dossier):
            element.hide()
        header_item = alcove.itemAt(0)
        if header_item and header_item.widget():
            header_item.widget().hide()
    workspace.addWidget(w.manga_dock)

    w.pages=QStackedWidget()
    w.pages.setMinimumWidth(250)
    workspace.addWidget(w.pages,1)
    build_archive_page(w)

    w.preview_panel=QFrame()
    w.preview_panel.setObjectName("previewPane")
    w.preview_panel.setMinimumWidth(260)
    preview=QVBoxLayout(w.preview_panel)
    preview.setContentsMargins(15,16,15,13)
    preview.setSpacing(10)
    heading=QHBoxLayout()
    heading.addWidget(make_label("Selected item","previewTitle"))
    heading.addStretch()
    w.preview_heading=make_label("プレビュー / PREVIEW","previewHeading")
    w.preview_heading.setToolTip("Preview / プレビュー")
    heading.addWidget(w.preview_heading)
    preview.addLayout(heading)
    border=QFrame()
    border.setObjectName("previewBorder")
    border.setMinimumHeight(200)
    border.setMaximumHeight(350)
    pb=QVBoxLayout(border)
    pb.setContentsMargins(4,4,4,4)
    w.preview_stack=QStackedWidget()
    w.preview_label=make_label("Select an item to preview","previewText")
    w.preview_label.setWordWrap(True)
    w.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
    w.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    w.preview_stack.addWidget(w.preview_label)
    w.preview_image_page=QWidget()
    pv=QVBoxLayout(w.preview_image_page)
    pv.setContentsMargins(1,1,1,1)
    w.preview_image=image_preview_class()
    pv.addWidget(w.preview_image,1)
    w.preview_dimensions=make_label("","previewDimensions")
    w.preview_dimensions.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pv.addWidget(w.preview_dimensions)
    w.preview_stack.addWidget(w.preview_image_page)
    pb.addWidget(w.preview_stack)
    preview.addWidget(border,2)
    w.preview_name=make_label("No selection","previewName")
    w.preview_name.setWordWrap(False)
    preview.addWidget(w.preview_name)
    w.preview_sub=make_label("Select a clipboard entry","previewSub")
    preview.addWidget(w.preview_sub)
    rule=QFrame()
    rule.setFixedHeight(1)
    rule.setStyleSheet("background:#49323D")
    preview.addWidget(rule)
    preview.addWidget(make_label("FILE DETAILS / 詳細","detailsHeading"))
    w.preview_meta={}
    for name in ("Type","Saved","Collection","Source","Tags"):
        row=QHBoxLayout()
        key=make_label(name,"metaKey")
        key.setFixedWidth(82)
        val=make_label("—","metaValue")
        val.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        row.addWidget(key)
        row.addWidget(val,1)
        w.preview_meta[name]=val
        preview.addLayout(row)
    preview.addStretch(1)
    buttons=QHBoxLayout()
    buttons.setSpacing(7)
    w.copy_action=QPushButton("♧  COPY")
    w.copy_action.setObjectName("previewCopy")
    w.copy_action.clicked.connect(w.copy_selected)
    buttons.addWidget(w.copy_action)
    w.pin_action=QPushButton("PIN")
    w.pin_action.setObjectName("previewAction")
    w.pin_action.clicked.connect(w.toggle_pin_selected)
    buttons.addWidget(w.pin_action)
    w.delete_action=QPushButton("DELETE")
    w.delete_action.setObjectName("previewAction")
    w.delete_action.clicked.connect(w.delete_selected)
    buttons.addWidget(w.delete_action)
    preview.addLayout(buttons)
    workspace.addWidget(w.preview_panel,1)

    dock=QFrame()
    dock.setObjectName("dock")
    w.dock_panel=dock
    dock.setFixedWidth(144)
    nav=QVBoxLayout(dock)
    nav.setContentsMargins(8,12,8,10)
    nav.setSpacing(5)
    nav.addWidget(make_label("MODULES / 機能","dockHeading"))
    w.nav_buttons={}
    # Every item uses an explicit English action and a matching Japanese label.
    # Short Japanese names keep both lines legible inside the 144px dock.
    for i,(label,icon,display,subtitle) in enumerate((
        ("Clipboard","▤","Clipboard","クリップボード"),
        ("Screenshots","▣","Screenshots","撮影画像"),
        ("Recordings","◉","Recordings","画面録画"),
        ("Secrets & Variables","♢","Vault","秘密保管庫"),
        ("Autosort","⇄","Autosort","自動仕分け"),
        ("Settings","⚙","Settings","設定"),
    )):
        btn=QPushButton(f"{icon}   {display}\n      {subtitle}")
        btn.setObjectName("nav")
        btn.setToolTip(f"{display} / {label}")
        btn.setProperty("dockDisplay", display)
        btn.setProperty("dockSubtitle", subtitle)
        btn.setProperty("dockIcon", icon)
        btn.setAccessibleName(label)
        btn.setCheckable(True)
        btn.setMinimumHeight(68)
        btn.clicked.connect(lambda _checked=False, index=i: w.open_section(index))
        w.nav_buttons[label]=btn
        nav.addWidget(btn)
    nav.addStretch()
    stamp=make_label("◇   Manage / 04\n管理","dockStamp")
    stamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
    nav.addWidget(stamp)
    workspace.addWidget(dock)
    root.addLayout(workspace,1)

    # Real actions, not demo button handlers.
    footer=QFrame()
    footer.setObjectName("footer")
    fl=QHBoxLayout(footer)
    fl.setContentsMargins(0,13,0,2)
    fl.setSpacing(0)
    w.footer_status=make_label("● Ready   |   HISTORY 00","footerStatus")
    w.footer_status.setMinimumWidth(110)
    fl.addWidget(w.footer_status,1)
    w.record_button=CrimsonFooterButton("●  Record Video\nREC / MP4 · GIF", primary=True)
    w.record_button.setObjectName("record")
    w.record_button.setFixedHeight(64)
    w.record_button.clicked.connect(lambda: w.choose_recording("MP4"))
    fl.addWidget(w.record_button,2)
    w.record_menu=CrimsonFooterArrow(primary=True)
    w.record_menu.setObjectName("recordArrow")
    w.record_menu.setText("▾")
    w.record_menu.setFixedHeight(64)
    w.record_menu.setFixedWidth(44)
    w.record_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    formats=QMenu(w.record_menu)
    formats.addAction("Record MP4").triggered.connect(lambda: w.choose_recording("MP4"))
    formats.addAction("Record GIF").triggered.connect(lambda: w.choose_recording("GIF"))
    w.record_menu.setMenu(formats)
    fl.addWidget(w.record_menu)
    fl.addSpacing(11)
    w.screenshot_button=CrimsonFooterButton("▣  Screenshot Area\nCAPTURE / REGION", primary=False)
    w.screenshot_button.setObjectName("screenshot")
    w.screenshot_button.setFixedHeight(64)
    w.screenshot_button.clicked.connect(w.choose_screenshot)
    fl.addWidget(w.screenshot_button,2)
    w.screenshot_menu=CrimsonFooterArrow(primary=False)
    w.screenshot_menu.setObjectName("shotArrow")
    w.screenshot_menu.setText("▾")
    w.screenshot_menu.setFixedHeight(64)
    w.screenshot_menu.setFixedWidth(44)
    w.screenshot_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    capture=QMenu(w.screenshot_menu)
    capture.addAction("Select area (default)").triggered.connect(w.choose_screenshot)
    capture.addAction("Full screen").triggered.connect(w.screenshot_full)
    w.screenshot_menu.setMenu(capture)
    fl.addWidget(w.screenshot_menu)
    fl.addStretch(1)
    root.addWidget(footer)
    w.setCentralWidget(shell)
    # Keep the actual monitor state visible; transient status-bar messages
    # must not replace ACTIVE/PAUSED/LOCKED with an unrelated notification.
    # The hidden native Qt status bar's latest message remains inspectable
    # in the footer tooltip.
    w.statusBar().messageChanged.connect(
        lambda s: w.footer_status.setToolTip(s) if s else None
    )
    w.statusBar().hide()
    return shell


def build_archive_page(w):
    page=QWidget()
    page.setObjectName("archivePage")
    layout=QVBoxLayout(page)
    layout.setContentsMargins(12,15,12,8)
    layout.setSpacing(12)
    header=QHBoxLayout()
    header_text=QVBoxLayout()
    header_text.setSpacing(5)
    header_text.addWidget(make_label("01 / CLIPBOARD TIMELINE","eyebrow"))
    w.archive_heading=make_label("Clipboard  ·  クリップボード","sectionTitle")
    header_text.addWidget(w.archive_heading)
    header.addLayout(header_text)
    header.addStretch()
    w.archive_date=make_label(datetime.now().strftime("%d %b %Y").upper(),"archiveDate")
    header.addWidget(w.archive_date)
    layout.addLayout(header)
    bin_row=QHBoxLayout()
    bin_row.setSpacing(0)
    w.tabs=QTabBar()
    w.tabs.setExpanding(False)
    w.tabs.setDrawBase(False)
    # Fixed content filters: top tabs are views, not storage folders.
    from .history_filters import populate_filter_tabs
    populate_filter_tabs(w.tabs)
    w.tabs.setToolTip("Filter all copied clips by content type")
    w.tabs.currentChanged.connect(w.refresh)
    bin_row.addWidget(w.tabs,1)
    layout.addLayout(bin_row)
    # Draw the search outline on a real QFrame. Qt can otherwise ignore a
    # QLineEdit's border radius on some X11 themes and render a square box.
    search_shell=GothicSearchCapsule()
    search_shell.setObjectName("archiveSearchCapsule")
    search_row=QHBoxLayout(search_shell)
    search_row.setContentsMargins(12,1,10,1)
    search_row.setSpacing(8)
    glyph=make_label("⌕","archiveSearchGlyph")
    glyph.setFixedWidth(16)
    search_row.addWidget(glyph)
    w.search=QLineEdit()
    w.search.setObjectName("archiveSearch")
    w.search.setStyleSheet(
        'QLineEdit {background:transparent;border:0;border-radius:0;'
        'color:#F7E9DD;font:13px "Georgia";padding:7px 0;}'
        'QLineEdit:focus {background:transparent;border:0;color:#FFF4E7;}'
    )
    w.search.setPlaceholderText("Search the archive…")
    w.search.textChanged.connect(w._schedule_history_search)
    search_row.addWidget(w.search,1)
    layout.addWidget(search_shell)
    controls=QHBoxLayout()
    controls.setSpacing(9)
    # Collection scope is secondary and independent of the content tabs.
    # Retain physical bins for Autosort and existing clip metadata without
    # treating those storage destinations as top-level navigation.
    w.bin_filter=QComboBox()
    w.bin_filter.setObjectName("collectionFilter")
    w.bin_filter.addItem("All collections", None)
    for name in w.store.bins():
        w.bin_filter.addItem(name, name)
    w.bin_filter.setToolTip(
        "Optional collection scope; top tabs always filter by content type"
    )
    w.bin_filter.currentIndexChanged.connect(w.refresh)
    controls.addWidget(make_label("COLLECTION","filterLabel"))
    controls.addWidget(w.bin_filter,1)
    add_bin=QPushButton("+")
    add_bin.setObjectName("addBin")
    add_bin.setToolTip("Create a collection for custom routing and Autosort")
    add_bin.clicked.connect(w.new_bin)
    controls.addWidget(add_bin)
    w.sort_combo=QComboBox()
    for display, key in (("Newest", "Latest first"), ("Best match", "Best match"), ("Oldest", "Oldest first"),
                         ("A–Z", "A–Z"), ("Z–A", "Z–A"), ("Numbered", "Numbered list")):
        w.sort_combo.addItem(display, key)
    w.sort_combo.setToolTip("Sorting: latest, oldest, alphabetical or numbered")
    w.sort_combo.currentIndexChanged.connect(w.refresh)
    controls.addWidget(w.sort_combo,1)
    w.count_label=make_label("00 / 00","counter")
    controls.addWidget(w.count_label)
    layout.addLayout(controls)

    # Organisational controls are separate from ordinary type/sort filters.
    # A second restrained row keeps the first row readable on laptop widths.
    organisers=QHBoxLayout()
    organisers.setSpacing(5)
    w.tag_filter=QComboBox()
    w.tag_filter.setObjectName("tagFilter")
    w.tag_filter.addItem("All tags", "")
    w.tag_filter.setToolTip("Show clips carrying a particular tag")
    w.tag_filter.currentIndexChanged.connect(w.refresh)
    organisers.addWidget(w.tag_filter, 2)
    w.favorites_filter=QCheckBox("♥ Favourites")
    w.favorites_filter.setObjectName("favoriteFilter")
    w.favorites_filter.setToolTip("Show only favourite clips")
    w.favorites_filter.toggled.connect(w.refresh)
    organisers.addWidget(w.favorites_filter, 2)
    w.templates_button=QPushButton("✧ Snippets")
    w.templates_button.setObjectName("organizerAction")
    w.templates_button.setToolTip("Open saved reusable text templates")
    w.templates_button.clicked.connect(w.show_templates)
    organisers.addWidget(w.templates_button, 1)
    w.queue_next_button=QPushButton("NEXT 0")
    w.queue_next_button.setObjectName("organizerAction")
    w.queue_next_button.setToolTip("Copy next queued item; paste it manually")
    w.queue_next_button.clicked.connect(w.queue_copy_next)
    w.queue_next_button.setEnabled(False)
    organisers.addWidget(w.queue_next_button, 1)
    layout.addLayout(organisers)
    w.history=QListWidget()
    w.history.setObjectName("clipHistory")
    w.history.setUniformItemSizes(True)
    w.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.history.setMouseTracking(True)
    w.history.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    w.history.setItemDelegate(CrimsonClipDelegate(w.history))
    w.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    w.history.customContextMenuRequested.connect(w.context_menu)
    w.history.itemDoubleClicked.connect(w.copy_clip)
    w.history.currentItemChanged.connect(w.preview_clip)
    layout.addWidget(w.history,1)
    w.pages.addWidget(page)
