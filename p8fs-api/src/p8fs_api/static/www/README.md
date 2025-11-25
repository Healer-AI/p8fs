# EEPIS Landing Page Designs

Two elegant landing page designs for EEPIS (eepis.ai) - a secure memory infrastructure platform with end-to-end encryption.

## Designs

### Version 1 - Modern Minimalist
**File:** `index-v1.html`

Light, gradient-based design with subtle geometric patterns. Features clean typography and a minimalist aesthetic. Best for emphasizing trust and simplicity.

Key elements:
- Gradient hero section with device mockup
- Card-based feature layout with accent borders
- Light color palette based on EEPIS brand colors
- Emphasis on readability and whitespace

### Version 2 - Dark Mode Bold
**File:** `index-v2.html`

Dark theme with bold typography and strong visual hierarchy. Features gradient backgrounds and prominent CTAs. Best for emphasizing technology and innovation.

Key elements:
- Dark gradient backgrounds with grid patterns
- Multi-device showcase (iPad + iPhone mockups)
- Bold statistics and data points
- Strong visual contrast

## Pages Included

- `index-v1.html` - Landing page version 1 (light theme)
- `index-v2.html` - Landing page version 2 (dark theme)
- `login.html` - Mobile authentication page with QR code and device code
- `contact.html` - Contact form and information
- `about.html` - Company information and system details
- `privacy.html` - Comprehensive privacy policy (zero-knowledge architecture)
- `terms.html` - Terms and conditions

## Color Palette

Based on EEPIS brand identity:

```css
--eepis-bg: #ECE0E8          /* Light background */
--eepis-primary: #1E0B36     /* Deep purple */
--eepis-secondary: #CA3782   /* Magenta */
--eepis-text: #230A1B        /* Dark text */
--eepis-text-light: #371e2f  /* Light text */
```

## Typography

Primary font: Inter (Google Fonts)
- Clean, modern sans-serif
- Excellent readability across all sizes
- Professional appearance

## Structure

```
eepis-landing/
├── assets/
│   └── images/
│       ├── logo.png          # Full EEPIS logo
│       └── logo-icon.png     # Icon only
├── css/
│   ├── common.css            # Shared styles (nav, footer, buttons)
│   ├── style-v1.css          # Version 1 specific styles
│   ├── style-v2.css          # Version 2 specific styles
│   └── pages.css             # Supporting page styles
├── index-v1.html
├── index-v2.html
├── login.html
├── contact.html
├── about.html
├── privacy.html
├── terms.html
└── README.md
```

## Key Features Highlighted

### REM Architecture
Resource-Entity-Moment system that extracts temporal narratives, identifies entities, and builds knowledge graphs from user content.

### Security Features
- End-to-end encryption with mobile-generated keypairs
- Zero-knowledge architecture (we cannot decrypt user content)
- OAuth 2.1 device flow authentication
- AES-256 encryption at rest
- TLS 1.3 with certificate pinning

### Platform Support
- iOS (iPhone and iPad)
- macOS
- Android

## Design Principles

1. **No emojis** - Professional, clean aesthetic
2. **Flexbox layouts** - Responsive, modern CSS
3. **Subtle patterns** - Visual interest without distraction
4. **Security emphasis** - Highlights privacy and encryption throughout
5. **Mobile-first** - Responsive design for all screen sizes

## Privacy & Security Documentation

Both the Privacy Policy and Terms & Conditions are comprehensive legal documents reflecting EEPIS's zero-knowledge architecture:

- Client-side encryption emphasis
- No password vulnerabilities (OAuth 2.1)
- User data ownership
- Right to deletion and data export
- Transparent technical measures

## Viewing the Pages

Simply open any HTML file in a modern web browser. All resources are referenced relatively, so the entire directory can be deployed to any web server.

For local development:
```bash
# Using Python
python3 -m http.server 8000

# Using Node.js
npx http-server

# Then visit http://localhost:8000
```

## Deployment Notes

- Update all `eepis.ai` references to actual domain
- Replace placeholder store badge links with real App Store/Play Store URLs
- Update contact email addresses (contact@, security@, privacy@, legal@)
- Add actual QR code generation for login page
- Implement actual form submission handlers
- Add analytics tracking if needed

## Browser Support

Designed for modern browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

Uses modern CSS features:
- CSS Grid
- Flexbox
- CSS Custom Properties (variables)
- Backdrop filters
- Gradient backgrounds

## Customization

To adapt the design:

1. **Colors:** Edit CSS variables in `common.css`
2. **Typography:** Change Google Fonts import in CSS files
3. **Layouts:** Modify flexbox/grid properties in respective CSS files
4. **Content:** Update HTML text directly
5. **Branding:** Replace logo files in `assets/images/`

## Accessibility

- Semantic HTML structure
- Proper heading hierarchy
- Alt text ready for images
- High contrast ratios
- Keyboard navigation support
- ARIA labels where needed

## Performance

- Minimal external dependencies (only Google Fonts)
- No JavaScript frameworks required
- Optimized CSS with minimal redundancy
- Fast load times
- Mobile-optimized assets

## License

Design created for EEPIS platform. All rights reserved.
