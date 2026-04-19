"""
Mittora — Centralized Theme Configuration
All color palettes, typography, spacing, and design tokens are defined here.
Change any value to propagate across the entire application instantly.

Core Palette:
  Light: #ffffff, #fdfbd4, #fef7e8  |  Accent border: #8b0403
  Dark:  #0e0e0e                    |  Accent border: #8b0403
"""

# ═══════════════════════════════════════════
#  SHARED TOKENS (theme-independent)
# ═══════════════════════════════════════════

FONT_FAMILY = "'Segoe UI', 'Inter', sans-serif"
FONT_FAMILY_MONO = "'Cascadia Code', 'Consolas', monospace"

FONT_SIZE_XS = "10px"
FONT_SIZE_SM = "11px"
FONT_SIZE_MD = "13px"
FONT_SIZE_LG = "14px"
FONT_SIZE_XL = "17px"
FONT_SIZE_2XL = "22px"
FONT_SIZE_3XL = "24px"

FONT_WEIGHT_NORMAL = "400"
FONT_WEIGHT_MEDIUM = "500"
FONT_WEIGHT_SEMIBOLD = "600"
FONT_WEIGHT_BOLD = "700"

RADIUS_SM = "5px"
RADIUS_MD = "8px"
RADIUS_LG = "10px"
RADIUS_XL = "12px"

SIDEBAR_WIDTH = 230
HEADER_HEIGHT = 80
NAV_BTN_HEIGHT = 44
MIN_WINDOW_W = 1060
MIN_WINDOW_H = 780

SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24
SPACING_2XL = 36

# Accent color — shared across both themes
ACCENT = "#8b0403"
ACCENT_LIGHT = "#a81a19"
ACCENT_DARK = "#6e0302"
ACCENT_GLOW = "rgba(139, 4, 3, 0.12)"
ACCENT_TEXT_ON = "#ffffff"


# ═══════════════════════════════════════════
#  LIGHT THEME
#  Canvas: #fef7e8 | Cards: #ffffff | Sidebar: #fdfbd4
# ═══════════════════════════════════════════

LIGHT = {
    # Primary accent (deep crimson)
    "primary":                ACCENT,
    "primary_container":      ACCENT,
    "primary_hover":          ACCENT_DARK,
    "primary_pressed":        "#520201",
    "primary_text_on":        ACCENT_TEXT_ON,

    # Secondary (muted warm)
    "secondary":              "#6e4b2a",
    "secondary_container":    "#fdfbd4",

    # Success / Error / Warning
    "success":                "#2e7d32",
    "success_hover":          "#1b5e20",
    "error":                  "#c62828",
    "error_hover":            "#b71c1c",
    "warning":                "#e65100",

    # Surfaces
    "background":             "#fef7e8",
    "surface":                "#fef7e8",
    "surface_container_lowest": "#ffffff",
    "surface_container_low":  "#fdfbd4",
    "surface_container":      "#faf5d0",
    "surface_container_high": "#f5efc8",
    "surface_container_highest": "#efe9c0",
    "surface_dim":            "#e8e0c0",
    "surface_variant":        "#f5efc8",

    # Text
    "on_surface":             "#1a1a1a",
    "on_surface_variant":     "#4a4438",
    "text_primary":           "#1a1a1a",
    "text_secondary":         "#4a4438",
    "text_muted":             "#7a7060",
    "text_placeholder":       "#9a9080",

    # Borders / Outlines — crimson accent
    "outline":                ACCENT,
    "outline_variant":        "#d4a0a0",
    "border":                 ACCENT,
    "border_subtle":          "#e8d8c0",

    # Sidebar
    "sidebar_bg":             "#fdfbd4",
    "sidebar_border":         ACCENT,
    "sidebar_hover":          "#faf5c8",
    "sidebar_active_bg":      "#f5efc0",
    "sidebar_active_border":  ACCENT,
    "sidebar_text":           "#5a5040",
    "sidebar_text_active":    ACCENT,

    # Content header
    "content_header_bg":      "#ffffff",
    "content_header_border":  ACCENT,

    # Inputs
    "input_bg":               "#ffffff",
    "input_border":           "#d0c8b0",
    "input_focus_border":     ACCENT,
    "input_focus_bg":         "#fef7e8",
    "input_disabled_bg":      "#f0e8d0",
    "input_disabled_text":    "#9a9080",

    # Buttons (base)
    "btn_bg":                 "#ffffff",
    "btn_border":             "#d0c8b0",
    "btn_hover_bg":           "#fdfbd4",
    "btn_hover_border":       ACCENT,
    "btn_text":               "#1a1a1a",

    # Table
    "table_bg":               "#ffffff",
    "table_border":           "#e0d8c0",
    "table_gridline":         "#f0e8d8",
    "table_header_bg":        "#fdfbd4",
    "table_header_text":      "#5a5040",
    "table_item_border":      "#f0e8d8",
    "table_selection_bg":     ACCENT_GLOW,
    "table_selection_text":   ACCENT,

    # GroupBox
    "group_bg":               "#ffffff",
    "group_border":           "#e0d8c0",
    "group_title_bg":         "#fdfbd4",
    "group_title_border":     "#d0c8b0",
    "group_title_text":       "#1a1a1a",
    "group_text":             "#4a4438",

    # TextEdit (Log)
    "log_bg":                 "#fdfbd4",
    "log_border":             "#e0d8c0",
    "log_text":               "#4a4438",

    # ScrollBar
    "scrollbar_handle":       "#d0c8b0",
    "scrollbar_handle_hover": ACCENT,

    # Slider
    "slider_groove":          "#e0d8c0",
    "slider_handle":          ACCENT,
    "slider_handle_hover":    ACCENT_DARK,
    "slider_sub_page":        ACCENT,

    # StatusBar
    "statusbar_bg":           "#fdfbd4",
    "statusbar_text":         "#7a7060",
    "statusbar_border":       "#e0d8c0",

    # Checkbox
    "checkbox_border":        "#d0c8b0",
    "checkbox_bg":            "#ffffff",
    "checkbox_checked_bg":    ACCENT,
    "checkbox_checked_border": ACCENT,

    # Selection
    "selection_bg":           ACCENT,
    "selection_text":         "#ffffff",

    # Misc
    "separator":              "#e0d8c0",
    "scheduler_active":       "#2e7d32",
}


# ═══════════════════════════════════════════
#  DARK THEME
#  Canvas: #0e0e0e | Accent border: #8b0403
# ═══════════════════════════════════════════

DARK = {
    # Primary accent (deep crimson)
    "primary":                ACCENT_LIGHT,
    "primary_container":      ACCENT,
    "primary_hover":          ACCENT_DARK,
    "primary_pressed":        "#520201",
    "primary_text_on":        ACCENT_TEXT_ON,

    # Secondary (muted warm)
    "secondary":              "#c0a080",
    "secondary_container":    "#2a2018",

    # Success / Error / Warning
    "success":                "#34d399",
    "success_hover":          "#059669",
    "error":                  "#ef4444",
    "error_hover":            "#dc2626",
    "warning":                "#e8a838",

    # Surfaces
    "background":             "#0e0e0e",
    "surface":                "#0e0e0e",
    "surface_container_lowest": "#0a0a0a",
    "surface_container_low":  "#141414",
    "surface_container":      "#1a1a1a",
    "surface_container_high": "#222222",
    "surface_container_highest": "#2a2a2a",
    "surface_dim":            "#0e0e0e",
    "surface_variant":        "#2a2a2a",

    # Text
    "on_surface":             "#e8e4dc",
    "on_surface_variant":     "#b8b0a0",
    "text_primary":           "#f0ece4",
    "text_secondary":         "#c0b8a8",
    "text_muted":             "#787068",
    "text_placeholder":       "#585048",

    # Borders / Outlines — crimson accent
    "outline":                ACCENT,
    "outline_variant":        "#4a2020",
    "border":                 ACCENT,
    "border_subtle":          "#1e1e1e",

    # Sidebar
    "sidebar_bg":             "#121212",
    "sidebar_border":         ACCENT,
    "sidebar_hover":          "#1a1a1a",
    "sidebar_active_bg":      "#1e1210",
    "sidebar_active_border":  ACCENT,
    "sidebar_text":           "#787068",
    "sidebar_text_active":    ACCENT_LIGHT,

    # Content header
    "content_header_bg":      "#121212",
    "content_header_border":  ACCENT,

    # Inputs
    "input_bg":               "#161616",
    "input_border":           "#2a2a2a",
    "input_focus_border":     ACCENT,
    "input_focus_bg":         "#1a1614",
    "input_disabled_bg":      "#101010",
    "input_disabled_text":    "#3a3a3a",

    # Buttons (base)
    "btn_bg":                 "#1a1a1a",
    "btn_border":             "#2a2a2a",
    "btn_hover_bg":           "#222222",
    "btn_hover_border":       ACCENT,
    "btn_text":               "#e8e4dc",

    # Table
    "table_bg":               "#121212",
    "table_border":           "#1e1e1e",
    "table_gridline":         "#1a1a1a",
    "table_header_bg":        "#161616",
    "table_header_text":      "#585048",
    "table_item_border":      "#1a1a1a",
    "table_selection_bg":     ACCENT_GLOW,
    "table_selection_text":   ACCENT_LIGHT,

    # GroupBox
    "group_bg":               "#121212",
    "group_border":           "#1e1e1e",
    "group_title_bg":         "#1a1a1a",
    "group_title_border":     "#2a2a2a",
    "group_title_text":       "#e8e4dc",
    "group_text":             "#c0b8a8",

    # TextEdit (Log)
    "log_bg":                 "#0a0a0a",
    "log_border":             "#1e1e1e",
    "log_text":               "#888078",

    # ScrollBar
    "scrollbar_handle":       "#2a2a2a",
    "scrollbar_handle_hover": ACCENT,

    # Slider
    "slider_groove":          "#1a1a1a",
    "slider_handle":          ACCENT,
    "slider_handle_hover":    ACCENT_DARK,
    "slider_sub_page":        ACCENT,

    # StatusBar
    "statusbar_bg":           "#0a0a0a",
    "statusbar_text":         "#484040",
    "statusbar_border":       "#1a1a1a",

    # Checkbox
    "checkbox_border":        "#2a2a2a",
    "checkbox_bg":            "#161616",
    "checkbox_checked_bg":    ACCENT,
    "checkbox_checked_border": ACCENT,

    # Selection
    "selection_bg":           ACCENT,
    "selection_text":         "#ffffff",

    # Misc
    "separator":              "#1e1e1e",
    "scheduler_active":       "#34d399",
}


# ═══════════════════════════════════════════
#  THEME BUILDER — generates full QSS
# ═══════════════════════════════════════════

def get_theme(name: str = "dark") -> dict:
    """Return the palette dict for the given theme name."""
    return DARK if name == "dark" else LIGHT


def build_stylesheet(theme_name: str = "dark") -> str:
    """
    Build a complete Qt stylesheet from the centralized palette.
    Every color references the theme dict so a single change propagates.
    """
    t = get_theme(theme_name)

    return f"""
        /* ══════════════════════════════════════
           MITTORA — {"Dark" if theme_name == "dark" else "Light"} Theme
           Accent: Deep Crimson #8b0403
           ══════════════════════════════════════ */

        QMainWindow {{
            background-color: {t["background"]};
            color: {t["text_primary"]};
            font-family: {FONT_FAMILY};
            font-size: {FONT_SIZE_MD};
        }}

        /* ── Sidebar ── */
        QFrame#sidebar {{
            background-color: {t["sidebar_bg"]};
            border-right: 1px solid {t["sidebar_border"]};
        }}
        QFrame#brandFrame {{ background: transparent; }}
        QLabel#brandIcon {{
            font-size: {FONT_SIZE_3XL};
            color: {t["primary_container"]};
        }}
        QLabel#brandLabel {{
            font-size: {FONT_SIZE_2XL};
            font-weight: {FONT_WEIGHT_BOLD};
            color: {t["text_primary"]};
            letter-spacing: 1px;
        }}
        QLabel#versionBadge {{
            font-size: {FONT_SIZE_XS};
            color: {t["text_muted"]};
            padding: 3px 8px;
            background: {t["surface_container"]};
            border-radius: 6px;
            border: 1px solid {t["border_subtle"]};
        }}
        QFrame#sidebarSep {{ background-color: {t["border"]}; }}
        QLabel#navSectionLabel {{
            font-size: {FONT_SIZE_XS};
            font-weight: {FONT_WEIGHT_BOLD};
            color: {t["text_muted"]};
            letter-spacing: 2px;
            padding-left: 24px;
        }}

        /* ── Nav Buttons ── */
        QPushButton#navBtn {{
            background: transparent;
            color: {t["sidebar_text"]};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 0px;
            text-align: left;
            padding-left: 24px;
            font-size: 13.5px;
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}
        QPushButton#navBtn:hover {{
            background: {t["sidebar_hover"]};
            color: {t["text_secondary"]};
            border-left: 3px solid {t["border_subtle"]};
        }}
        QPushButton#navBtn:checked {{
            background: {t["sidebar_active_bg"]};
            color: {t["sidebar_text_active"]};
            border-left: 3px solid {t["sidebar_active_border"]};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}

        /* ── Sidebar Footer ── */
        QFrame#sidebarFooter {{ border-top: 1px solid {t["border"]}; }}
        QLabel#schedulerStatus {{
            font-size: {FONT_SIZE_MD};
            color: {t["scheduler_active"]};
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}

        /* ── Content Area ── */
        QFrame#contentFrame {{ background-color: {t["background"]}; }}
        QFrame#contentHeader {{
            background-color: {t["content_header_bg"]};
            border-bottom: 1px solid {t["content_header_border"]};
        }}
        QLabel#pageTitle {{
            font-size: {FONT_SIZE_3XL};
            font-weight: {FONT_WEIGHT_BOLD};
            color: {t["text_primary"]};
            letter-spacing: 0.3px;
        }}
        QLabel#headerInfo {{
            font-size: {FONT_SIZE_SM};
            color: {t["text_muted"]};
            padding: 6px 14px;
            background: {t["surface_container"]};
            border-radius: {RADIUS_MD};
            border: 1px solid {t["border_subtle"]};
        }}
        QWidget#pageContainer {{ background-color: {t["background"]}; }}

        /* ── GroupBox ── */
        QGroupBox {{
            font-size: {FONT_SIZE_LG};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            color: {t["group_text"]};
            border: 1px solid {t["group_border"]};
            border-radius: {RADIUS_XL};
            margin-top: 18px;
            padding-top: 28px;
            background-color: {t["group_bg"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 5px 16px;
            left: 16px;
            background-color: {t["group_title_bg"]};
            border-radius: {RADIUS_MD};
            border: 1px solid {t["group_title_border"]};
            color: {t["group_title_text"]};
        }}

        /* ── Inputs ── */
        QLineEdit, QSpinBox, QComboBox, QTimeEdit {{
            background-color: {t["input_bg"]};
            border: 1px solid {t["input_border"]};
            border-radius: {RADIUS_MD};
            padding: 9px 14px;
            color: {t["text_primary"]};
            font-size: {FONT_SIZE_MD};
            selection-background-color: {t["selection_bg"]};
            selection-color: {t["selection_text"]};
            min-height: 20px;
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {{
            border-color: {t["input_focus_border"]};
            background-color: {t["input_focus_bg"]};
        }}
        QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
            background-color: {t["input_disabled_bg"]};
            color: {t["input_disabled_text"]};
            border-color: {t["border_subtle"]};
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {t["input_bg"]};
            color: {t["text_primary"]};
            border: 1px solid {t["input_border"]};
            selection-background-color: {t["selection_bg"]};
            selection-color: {t["selection_text"]};
            border-radius: {RADIUS_MD};
            padding: 4px;
        }}

        /* ── Buttons ── */
        QPushButton {{
            background-color: {t["btn_bg"]};
            color: {t["btn_text"]};
            border: 1px solid {t["btn_border"]};
            border-radius: {RADIUS_MD};
            padding: 9px 22px;
            font-weight: {FONT_WEIGHT_MEDIUM};
            font-size: {FONT_SIZE_MD};
            min-height: 18px;
        }}
        QPushButton:hover {{
            background-color: {t["btn_hover_bg"]};
            border-color: {t["btn_hover_border"]};
            color: {t["text_primary"]};
        }}
        QPushButton:pressed {{
            background-color: {t["primary_container"]};
            color: {t["primary_text_on"]};
            border-color: {t["primary_container"]};
        }}
        QPushButton#primaryBtn {{
            background-color: {t["primary_container"]};
            border: none;
            color: {t["primary_text_on"]};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#primaryBtn:hover {{ background-color: {t["primary_hover"]}; }}
        QPushButton#primaryBtn:pressed {{ background-color: {t["primary_pressed"]}; }}
        QPushButton#dangerBtn {{
            background-color: {t["error"]};
            border: none;
            color: white;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#dangerBtn:hover {{ background-color: {t["error_hover"]}; }}
        QPushButton#successBtn {{
            background-color: {t["success"]};
            border: none;
            color: white;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#successBtn:hover {{ background-color: {t["success_hover"]}; }}

        /* ── Theme Toggle Buttons ── */
        QPushButton#themeBtn {{
            background-color: {t["btn_bg"]};
            border: 1px solid {t["btn_border"]};
            color: {t["text_secondary"]};
            border-radius: {RADIUS_MD};
            padding: 8px 18px;
            font-weight: {FONT_WEIGHT_MEDIUM};
        }}
        QPushButton#themeBtn:hover {{
            background-color: {t["btn_hover_bg"]};
            border-color: {t["primary_container"]};
        }}
        QPushButton#themeBtnActive {{
            background-color: {t["primary_container"]};
            border: none;
            color: {t["primary_text_on"]};
            border-radius: {RADIUS_MD};
            padding: 8px 18px;
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}

        /* ── Header Theme Toggle ── */
        QPushButton#themeToggleBtn {{
            background-color: {t["surface_container"]};
            border: 1px solid {t["primary_container"]};
            color: {t["text_primary"]};
            border-radius: 20px;
            font-size: {FONT_SIZE_SM};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
            padding: 0px;
        }}
        QPushButton#themeToggleBtn:hover {{
            background-color: {t["primary_container"]};
            color: {t["primary_text_on"]};
            border-color: {t["primary_container"]};
        }}
        QPushButton#themeToggleBtn:pressed {{
            background-color: {t["primary_pressed"]};
            color: {t["primary_text_on"]};
        }}

        /* ── Checkbox ── */
        QCheckBox {{
            color: {t["text_secondary"]};
            spacing: 10px;
            font-size: {FONT_SIZE_MD};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {t["checkbox_border"]};
            border-radius: {RADIUS_SM};
            background-color: {t["checkbox_bg"]};
        }}
        QCheckBox::indicator:checked {{
            background-color: {t["checkbox_checked_bg"]};
            border-color: {t["checkbox_checked_border"]};
        }}
        QCheckBox::indicator:hover {{ border-color: {t["primary_container"]}; }}

        /* ── Table ── */
        QTableWidget {{
            background-color: {t["table_bg"]};
            border: 1px solid {t["table_border"]};
            border-radius: {RADIUS_LG};
            gridline-color: {t["table_gridline"]};
            color: {t["text_primary"]};
            font-size: {FONT_SIZE_MD};
        }}
        QTableWidget::item {{
            padding: 10px 8px;
            border-bottom: 1px solid {t["table_item_border"]};
        }}
        QTableWidget::item:selected {{
            background-color: {t["table_selection_bg"]};
            color: {t["table_selection_text"]};
        }}
        QHeaderView::section {{
            background-color: {t["table_header_bg"]};
            color: {t["table_header_text"]};
            border: none;
            border-bottom: 2px solid {t["table_border"]};
            padding: 12px 8px;
            font-weight: {FONT_WEIGHT_BOLD};
            font-size: {FONT_SIZE_SM};
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* ── TextEdit (Log) ── */
        QTextEdit {{
            background-color: {t["log_bg"]};
            border: 1px solid {t["log_border"]};
            border-radius: {RADIUS_LG};
            color: {t["log_text"]};
            font-family: {FONT_FAMILY_MONO};
            font-size: {FONT_SIZE_SM};
            padding: 12px;
        }}

        /* ── ScrollBar ── */
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            border-radius: 3px;
            margin: 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t["scrollbar_handle"]};
            border-radius: 3px;
            min-height: 40px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t["scrollbar_handle_hover"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 6px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t["scrollbar_handle"]};
            border-radius: 3px;
            min-width: 40px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {t["scrollbar_handle_hover"]}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        /* ── Slider ── */
        QSlider::groove:horizontal {{
            background: {t["slider_groove"]};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {t["slider_handle"]};
            width: 18px;
            height: 18px;
            margin: -6px 0;
            border-radius: 9px;
        }}
        QSlider::handle:horizontal:hover {{ background: {t["slider_handle_hover"]}; }}
        QSlider::sub-page:horizontal {{
            background: {t["slider_sub_page"]};
            border-radius: 3px;
        }}

        /* ── StatusBar ── */
        QStatusBar {{
            background-color: {t["statusbar_bg"]};
            color: {t["statusbar_text"]};
            border-top: 1px solid {t["statusbar_border"]};
            font-size: {FONT_SIZE_SM};
            padding: 2px 8px;
        }}

        /* ── Labels ── */
        QLabel {{ color: {t["text_secondary"]}; }}
        QLabel#sectionTitle {{
            font-size: {FONT_SIZE_XL};
            font-weight: {FONT_WEIGHT_BOLD};
            color: {t["text_primary"]};
        }}
        QLabel#sectionDesc {{
            font-size: {FONT_SIZE_SM};
            color: {t["text_muted"]};
        }}
        QLabel#fieldHint {{
            font-size: {FONT_SIZE_SM};
            color: {t["text_muted"]};
            font-style: italic;
        }}
        QLabel#statusActive {{
            color: {t["scheduler_active"]};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QLabel#statusInactive {{
            color: {t["error"]};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}

        /* ── Misc ── */
        QFrame#separator {{
            background-color: {t["separator"]};
            max-height: 1px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}

        /* ── Dialog ── */
        QDialog {{
            background-color: {t["background"]};
            color: {t["text_primary"]};
            font-family: {FONT_FAMILY};
        }}
        QMessageBox {{
            background-color: {t["background"]};
            color: {t["text_primary"]};
        }}

        /* ── AI Assistant Chat Tab ── */
        QFrame#aiTopBar {{
            background-color: {t["surface_container_low"]};
            border-bottom: 1px solid {t["border_subtle"]};
        }}
        QLabel#aiTopLabel {{
            color: {t["text_secondary"]};
            font-size: {FONT_SIZE_SM};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QLabel#aiStatusLabel {{
            color: {t["text_muted"]};
            font-size: {FONT_SIZE_SM};
        }}
        QTextBrowser#aiChatDisplay {{
            background: {t["background"]};
            border: none;
            padding: 20px 40px;
            font-family: {FONT_FAMILY};
            font-size: {FONT_SIZE_MD};
            color: {t["text_primary"]};
        }}
        QFrame#aiInputBar {{
            background-color: {t["surface_container_low"]};
            border-top: 1px solid {t["border_subtle"]};
        }}
        QLineEdit#aiChatInput {{
            background-color: {t["input_bg"]};
            border: 1px solid {t["input_border"]};
            border-radius: 22px;
            padding: 0 20px;
            font-size: {FONT_SIZE_MD};
            color: {t["text_primary"]};
        }}
        QLineEdit#aiChatInput:focus {{
            border-color: {t["primary"]};
        }}
        QPushButton#aiSendBtn {{
            background-color: {t["primary_container"]};
            color: {t["primary_text_on"]};
            border: none;
            border-radius: 22px;
            font-size: {FONT_SIZE_MD};
            font-weight: {FONT_WEIGHT_SEMIBOLD};
        }}
        QPushButton#aiSendBtn:hover {{
            background-color: {t["primary_hover"]};
        }}
        QPushButton#aiSendBtn:disabled {{
            background-color: {t["surface_container_high"]};
            color: {t["text_muted"]};
        }}
        QPushButton#aiClearBtn {{
            background: transparent;
            color: {t["text_muted"]};
            border: none;
            font-size: {FONT_SIZE_SM};
            padding: 0 8px;
        }}
        QPushButton#aiClearBtn:hover {{
            color: {t["error"]};
        }}
        QLabel#aiModelLabel {{
            color: {t["text_muted"]};
            font-size: {FONT_SIZE_XS};
        }}
    """
