
You are a **senior UI/UX designer and product designer** responsible for completely rethinking and modernising the user interface and user experience of this application.

The current application is functional, but the UI/UX feels basic, inconsistent, and outdated. I do **not** want a minor visual cleanup. I want a **major UI/UX redesign of the entire application**, including its layouts, navigation, information hierarchy, page flow, spacing, cards, sidebars, forms, responsiveness, and overall interaction experience.

### Main Problems With the Current UI

The current application has several UX issues:

* There are very few or no obvious **Back / Previous navigation controls**, making it difficult for users to understand where they are or return to a previous step.
* Page formatting is inconsistent.
* Padding, spacing, margins, alignment, and visual hierarchy need significant improvement.
* Cards are not consistently sized or positioned.
* Some cards contain too much information while others waste space.
* The sidebar feels basic and needs a complete redesign.
* There is currently no proper **Light Mode / Dark Mode** experience.
* Many pages are unnecessarily long.
* Users often have to scroll extensively just to reach the next action or next step.
* Important actions can appear too far down the page.
* Page layouts do not make efficient use of available desktop screen space.
* There is not enough distinction between primary information, secondary information, actions, statuses, and navigation.
* The overall user flow does not feel polished or intuitive.
* The application currently feels more like a functional internal tool than a professionally designed modern product.

### Your Goal

Redesign the application so it feels like a **modern, polished, premium SaaS/dashboard product**.

The interface should feel:

* Clean
* Modern
* Professional
* Minimal but not empty
* Easy to understand
* Fast to navigate
* Visually consistent
* Responsive
* Accessible
* Comfortable for prolonged use
* Optimised for both desktop and smaller screens

Do not simply redesign individual components independently. Think about the **complete user journey and application flow**.

### 1. Redesign the Overall Application Structure

First analyse the current application structure and identify:

* Main navigation areas
* Secondary navigation
* Pages
* Subpages
* Workflows
* Multi-step processes
* Forms
* Dashboards
* Tables
* Detail pages
* Settings pages
* Modals
* User actions

Then propose a more logical information architecture.

Ask:

* What should remain in the sidebar?
* What belongs in the top navigation?
* What can be grouped?
* What can be hidden until needed?
* What should be displayed as tabs?
* What should be a separate page?
* What should be a modal or drawer?
* What should become a multi-step workflow?

Reduce unnecessary navigation complexity.

### 2. Completely Redesign the Sidebar

The sidebar needs a major redesign.

Create a modern navigation sidebar with:

* Clear navigation hierarchy
* Consistent icons
* Proper spacing
* Active page highlighting
* Hover states
* Section grouping
* Expandable/collapsible groups where appropriate
* Optional collapsed sidebar mode
* Tooltips when collapsed
* Clear distinction between main navigation and settings/account controls

The sidebar should not feel cluttered.

Where appropriate, organise navigation into categories such as:

Main
Operations
Analytics
Management
Settings

Do not use these exact categories unless they make sense for the actual system.

### 3. Improve Navigation and Back Navigation

Every page should provide clear navigation context.

Introduce appropriate combinations of:

* Back buttons
* Breadcrumbs
* Page titles
* Parent-page navigation
* Tabs
* Step indicators
* Previous / Next controls

For example:

← Back to Customers

Dashboard / Customers / Customer Details

Users should never feel trapped inside a page or wonder how to return.

### 4. Reduce Excessive Scrolling

One of the biggest problems is that users currently have to scroll too much.

Reorganise long pages.

Possible techniques include:

* Tabs
* Accordions
* Sections
* Two-column layouts
* Three-column dashboard layouts
* Sticky action bars
* Sticky headers
* Side panels
* Drawers
* Modals
* Expandable sections
* Progressive disclosure
* Paginated data
* Step-based workflows

Do not force users to scroll through large amounts of information just to reach the next action.

Important actions should remain visible or easily accessible.

### 5. Redesign Cards

Redesign the application's card system.

Cards should have:

* Consistent border radius
* Consistent padding
* Proper spacing
* Consistent shadows/borders
* Clear headings
* Supporting text hierarchy
* Proper alignment
* Appropriate card sizes

Avoid creating huge cards for small amounts of information.

Avoid creating too many tiny cards.

Use cards only when they improve information grouping.

For dashboards, consider:

* KPI cards
* Status cards
* Activity cards
* Charts
* Progress cards
* Quick-action cards

Maintain consistent sizing across card groups.

### 6. Improve Page Layouts

Use screen space more intelligently.

Instead of making everything vertically stacked:

Use:

* CSS grids
* Responsive columns
* Split layouts
* Master-detail layouts
* Sidebar detail panels
* Tabs
* Inline controls

Desktop pages should properly utilise available horizontal space.

However, do not overcrowd the interface.

Maintain strong whitespace and visual hierarchy.

### 7. Introduce Proper Light Mode and Dark Mode

Design a complete theme system.

Create:

Light Mode

and

Dark Mode

Both themes should feel intentionally designed.

Do not simply invert colours.

Define appropriate theme tokens for:

* Background
* Surface
* Elevated surface
* Cards
* Borders
* Primary text
* Secondary text
* Muted text
* Primary colour
* Accent colour
* Success
* Warning
* Error
* Info
* Hover states
* Selected states
* Disabled states

Provide a theme switcher.

Prefer respecting the user's system theme initially if possible.

### 8. Improve Typography

Create a consistent typography hierarchy.

For example:

Page Title
Section Heading
Card Heading
Body Text
Secondary Text
Caption
Metadata
Labels

Avoid oversized headings that unnecessarily consume vertical space.

Keep text readable and well spaced.

### 9. Improve Forms

Redesign forms to feel modern and efficient.

Improve:

* Labels
* Inputs
* Select fields
* Checkboxes
* Radio controls
* Date selectors
* Search inputs
* Validation messages
* Required indicators
* Help text
* Input grouping

Use multi-column forms on desktop where appropriate.

Do not create extremely long single-column forms unless necessary.

For larger forms, introduce logical sections or multi-step flows.

### 10. Improve Multi-Step Workflows

If a task contains several steps, use a proper stepper.

Example:

1. Details
2. Configuration
3. Review
4. Confirmation

Provide:

Back

Continue

Save Draft

Cancel

where appropriate.

Users should always know:

Where they are
What they have completed
What happens next

### 11. Improve Buttons and Actions

Create a clear action hierarchy.

Use:

Primary button

Secondary button

Tertiary / ghost button

Danger button

Icon button

Avoid showing several equally prominent buttons.

The primary action should always be visually obvious.

For long pages, consider sticky action bars so users do not need to scroll to the bottom to continue.

### 12. Improve Tables and Data Displays

Redesign tables for better usability.

Consider:

* Sticky table headers
* Search
* Filters
* Sorting
* Pagination
* Row actions
* Bulk actions
* Status badges
* Column controls
* Responsive table behaviour

Do not overload tables with unnecessary columns.

Use drawers or detail pages for secondary information.

### 13. Improve Empty, Loading and Error States

Design proper states for:

Loading

Empty data

No search results

Errors

Success

Permissions

Offline/network issues

Do not leave blank sections with no explanation.

### 14. Responsive Design

The redesigned application must work properly on:

Large desktop

Laptop

Tablet

Mobile

Do not simply shrink the desktop interface.

Navigation and layout should adapt intelligently.

The sidebar may become a drawer on smaller screens.

Cards should reflow.

Tables should adapt.

Forms should transition from multi-column to single-column layouts.

### 15. Accessibility

Follow accessibility best practices.

Ensure:

* Good colour contrast
* Visible focus states
* Keyboard navigation
* Proper labels
* Reasonable click/touch target sizes
* Accessible icons
* Error messages that do not rely only on colour

### 16. Create a Consistent Design System

Define reusable UI standards instead of styling every page independently.

Create consistent rules for:

Spacing

Borders

Border radius

Shadows

Typography

Colours

Buttons

Inputs

Cards

Badges

Tabs

Modals

Drawers

Tables

Tooltips

Navigation

Use reusable components wherever possible.

### 17. Improve the User Flow

Do not only focus on visuals.

Analyse every major workflow.

For every workflow ask:

What is the user's goal?

What information do they need?

What is the primary action?

Which information can be hidden until needed?

Can the number of clicks be reduced?

Can unnecessary steps be removed?

Can the user complete the task without excessive scrolling?

Where could the user become confused?

Redesign the flow accordingly.

### Design Direction

The final visual direction should resemble a polished modern SaaS product.

Think along the quality level of products such as:

Linear
Stripe Dashboard
Vercel
Notion
Raycast
Modern enterprise dashboards

Use these only as inspiration for quality and usability.

Do not directly copy their designs.

### Important

Do **not** simply:

Change colours.

Add rounded corners.

Add shadows.

Make cards prettier.

This needs to be a genuine **UX redesign**.

Restructure pages where necessary.

Move components.

Reduce page length.

Introduce better navigation.

Improve flows.

Remove redundant UI.

Improve information hierarchy.

Create reusable components.

The objective is to make the application significantly easier and more enjoyable to use.

### Before Implementing

First inspect the current application.

Understand:

* Existing pages
* Existing components
* Existing workflows
* Existing navigation
* Existing design system
* Existing responsive behaviour
* Existing frontend framework and component libraries

Then create a redesign strategy.

For each important page, determine:

Current UX problem → Proposed UX solution → New layout/flow

Once the new direction is clear, implement the redesign consistently across the application.

Do not redesign one page while leaving the rest with the old style.

The final result should feel like **one coherent product designed by one design team**.
