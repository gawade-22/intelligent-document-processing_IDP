import React from 'react';

/**
 * Original IDP Branding Logo
 * Professional blue-based geometric emblem combining document structure with AI intelligent processing nodes.
 */
export default function IdpLogo({ size = 32, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`idp-brand-logo ${className}`}
      aria-label="IDP - Intelligent Document Processing"
    >
      <defs>
        <linearGradient id="idpGradPrimary" x1="2" y1="2" x2="34" y2="34" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#1e40af" />
          <stop offset="50%" stopColor="#1a56db" />
          <stop offset="100%" stopColor="#2563eb" />
        </linearGradient>
        <linearGradient id="idpSparkGrad" x1="16" y1="10" x2="30" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60a5fa" />
          <stop offset="100%" stopColor="#93c5fd" />
        </linearGradient>
      </defs>

      {/* Rounded Container Box */}
      <rect
        x="2"
        y="2"
        width="32"
        height="32"
        rx="8"
        fill="url(#idpGradPrimary)"
        stroke="#1d4ed8"
        strokeWidth="1"
      />

      {/* Document Fold Outline */}
      <path
        d="M10 9C10 7.89543 10.8954 7 12 7H20L26 13V27C26 28.1046 25.1046 29 24 29H12C10.8954 29 10 28.1046 10 27V9Z"
        fill="#ffffff"
        fillOpacity="0.15"
        stroke="#ffffff"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />

      {/* Document Fold Corner */}
      <path
        d="M20 7V13H26"
        stroke="#ffffff"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Processing Horizontal Lines */}
      <path
        d="M14 17H19M14 21H22M14 25H18"
        stroke="#ffffff"
        strokeWidth="1.5"
        strokeLinecap="round"
      />

      {/* AI Intelligence Spark / Node */}
      <circle cx="24" cy="22" r="3.5" fill="#60a5fa" stroke="#ffffff" strokeWidth="1.5" />
      <circle cx="24" cy="22" r="1.5" fill="#ffffff" />
    </svg>
  );
}
