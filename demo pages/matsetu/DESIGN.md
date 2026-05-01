---
name: MatSetu
colors:
  surface: '#faf9fe'
  surface-dim: '#dad9de'
  surface-bright: '#faf9fe'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f8'
  surface-container: '#eeedf2'
  surface-container-high: '#e9e7ec'
  surface-container-highest: '#e3e2e7'
  on-surface: '#1a1b1f'
  on-surface-variant: '#44474f'
  inverse-surface: '#2f3034'
  inverse-on-surface: '#f1f0f5'
  outline: '#747780'
  outline-variant: '#c4c6d0'
  surface-tint: '#425e91'
  primary: '#002452'
  on-primary: '#ffffff'
  primary-container: '#1b3a6b'
  on-primary-container: '#89a5dd'
  inverse-primary: '#acc7ff'
  secondary: '#0051d5'
  on-secondary: '#ffffff'
  secondary-container: '#316bf3'
  on-secondary-container: '#fefcff'
  tertiary: '#3c1e00'
  on-tertiary: '#ffffff'
  tertiary-container: '#5b3000'
  on-tertiary-container: '#d7985f'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d7e2ff'
  primary-fixed-dim: '#acc7ff'
  on-primary-fixed: '#001a40'
  on-primary-fixed-variant: '#294678'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#ffdcc1'
  tertiary-fixed-dim: '#fcb87d'
  on-tertiary-fixed: '#2e1500'
  on-tertiary-fixed-variant: '#693c0a'
  background: '#faf9fe'
  on-background: '#1a1b1f'
  surface-variant: '#e3e2e7'
typography:
  h1:
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  h2:
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  h3:
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-base:
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-bold:
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  button:
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  sidebar-width: 280px
  container-padding: 32px
  gutter: 24px
  stack-sm: 4px
  stack-md: 12px
  stack-lg: 24px
---

## Brand & Style

The brand personality of the design system is defined by **Institutional Authority** and **Operational Transparency**. As a government election management platform, the visual language must evoke absolute trust, stability, and precision. The target audience—election officials and administrators—requires an environment that minimizes cognitive load during high-stakes tasks.

The style is **Corporate / Modern (Flat)**. It intentionally avoids trends like glassmorphism or neomorphism to remain accessible and timeless. By utilizing a flat aesthetic with high-contrast borders rather than shadows, the design system ensures clarity across various display qualities, emphasizing functionality over decoration. The emotional response is one of calm, professional reliability.

## Colors

The palette is anchored by **Deep Navy Blue (#1B3A6B)**, a color synonymous with stability and governance. This is used for structural elements like the sidebar and primary navigation to provide a solid frame for the application.

**Bright Blue (#2563EB)** serves as the accent color, reserved exclusively for interactive elements and calls to action (CTAs). This ensures that "where to click" is never in doubt. The semantic colors for success, warning, and danger follow standard government accessibility guidelines to ensure critical status updates are immediately recognizable. Surfaces use a near-white grey to reduce eye strain, while cards are pure white with subtle borders to define information hierarchy without the need for depth-based effects.

## Typography

The design system utilizes **Public Sans**, an open-source typeface designed specifically for government interfaces. It provides a clean, neutral, and highly readable foundation that feels institutional yet modern.

Typography is treated with a strict hierarchy to manage complex data. Headlines use a heavier weight and tighter letter spacing to appear authoritative. Body text is set with generous line heights to ensure readability during prolonged administrative use. Labels and metadata use a smaller, slightly tracked-out uppercase style to differentiate them from actionable or primary content.

## Layout & Spacing

This design system employs a **Fixed-Sidebar Fluid-Content** layout model. The primary navigation is anchored to the left in a 280px navy column, providing a persistent "source of truth" for the user's location.

The main content area follows an 8px rhythmic grid. All padding, margins, and component dimensions are multiples of 8px to ensure visual harmony. For data-heavy pages, a 12-column grid is used with 24px gutters to allow for flexible dashboard layouts. Whitespace is used strategically to group related information, favoring "Stack" layouts for vertical forms and "Grid" layouts for metric cards.

## Elevation & Depth

In alignment with the "High-Trust / Government-Grade" style, this design system rejects shadows and blurs. Depth is conveyed entirely through **Tonal Layers and Bold Outlines**.

1.  **Level 0 (Base):** The #F8FAFC background acts as the canvas.
2.  **Level 1 (Content):** Cards and main panels are white with a 1px solid #E2E8F0 border.
3.  **Active State:** Elements being interacted with (like active nav items or focused inputs) use the Accent Blue (#2563EB) or a light tinted fill (#EFF6FF) to denote focus.

This "Flat Depth" approach ensures that the UI remains crisp on low-resolution monitors often found in field offices, while maintaining a sophisticated, modern professional look.

## Shapes

The shape language is **Structured and Approachable**. A dual-radius system is implemented to distinguish between structural containers and interactive components.

Interactive elements like buttons, input fields, and tags utilize an **8px radius**. This provides a modern, soft feel without appearing overly "bubbly" or informal. Larger containers, specifically informational cards, use a **12px radius**. This slight increase in rounding helps to visually encapsulate grouped data and creates a clear distinction between the "page architecture" and the "functional tools" contained within it.

## Components

### Buttons
- **Primary:** Solid #1B3A6B with white text. Used for the main action of a page.
- **Secondary:** White background, 1px #E2E8F0 border, #1E293B text.
- **CTA:** Solid #2563EB for high-priority task triggers (e.g., "Submit Results").
- **State:** No shadows on hover; instead, use a 10% black overlay or a slightly darker shade of the base color.

### Input Fields
- Standard height: 40px.
- Border: 1px #E2E8F0; Focus: 2px #2563EB.
- Labels are always positioned above the field in `label-bold` style.

### Cards
- Background: #FFFFFF.
- Border: 1px #E2E8F0.
- Padding: 24px internal padding.
- Header: Optional 1px bottom border to separate card title from content.

### Sidebar Items
- Active State: Background #2563EB (Accent) with a thick 4px left-accent bar in white.
- Inactive State: Transparent background with #CBD5E1 (muted white/grey) text and icons.

### Status Chips
- Small, 4px radius, using semantic colors with a 10% opacity background and 100% opacity text for high legibility (e.g., Success: Background #DCFCE7, Text #15803D).

### Data Tables
- Header: #F8FAFC background, `label-bold` text.
- Rows: 1px bottom border #E2E8F0, no alternating row colors.