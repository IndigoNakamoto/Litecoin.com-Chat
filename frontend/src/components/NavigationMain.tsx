'use client';

import siteMetadata from '@/data/siteMetadata';

import HorizontalSocialIcons from '@/components/HorizontalSocialIcons';
import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react';
import { useScrollContext } from '@/contexts/ScrollContext';
const LitecoinLogo = ({ width, height }: { width: number; height: number }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 293.6 82.7"
    width={width}
    height={height}
    role="img"
    aria-label="Litecoin"
  >
    <path
      fill="currentColor"
      d="M41.3,0C18.5,0,0,18.5,0,41.3s18.5,41.3,41.3,41.3s41.3-18.5,41.3-41.3l0,0C82.7,18.5,64.2,0,41.3,0z M42,42.7l-4.3,14.5h23
	c0.7,0,1.2,0.5,1.2,1.2c0,0.1,0,0.2,0,0.3l-2,6.9c-0.2,0.7-0.8,1.1-1.5,1.1H23.2l5.9-20.1l-6.6,2L24,44l6.6-2l8.3-28.2
	c0.2-0.7,0.8-1.1,1.5-1.1h8.9c0.7,0,1.2,0.5,1.2,1.2c0,0.1,0,0.2,0,0.3l-7,23.8l6.6-2l-1.4,4.8L42,42.7z"
    />
    <path
      fill="currentColor"
      d="M106.6,12.5H104c-0.5,0-0.8,0.3-0.9,0.8c0,0,0,0,0,0L96.5,66c-0.1,0.5,0.1,0.8,0.6,0.8h2.6c0.4,0.1,0.8-0.2,0.9-0.7
	c0,0,0-0.1,0-0.1l6.7-52.7C107.4,12.8,107.1,12.5,106.6,12.5z"
    />
    <path
      fill="currentColor"
      d="M120,27.7h-2.6c-0.4,0-0.8,0.3-0.9,0.7c0,0,0,0,0,0.1L111.8,66c-0.1,0.5,0.2,0.8,0.7,0.8h2.6c0.4,0.1,0.8-0.2,0.9-0.7
	c0,0,0-0.1,0-0.1l4.7-37.5C120.7,28,120.6,27.7,120,27.7z"
    />
    <path
      fill="currentColor"
      d="M232.4,27.1c-6.8-0.2-12.8,4.4-14.5,11.1c-0.7,3-1.2,6-1.6,9.1c-0.4,3-0.7,6-0.7,9.1c-0.1,3,1.1,5.9,3.2,8
	c2.1,2,4.9,3,8.6,3c3.3,0.1,6.6-1,9.2-3c2.6-2,4.4-4.8,5.2-8c0.7-3,1.3-6,1.6-9.1c0.4-3,0.6-6.1,0.7-9.1c0.1-3-1-5.9-3.1-8
	C238.5,28,235.5,26.9,232.4,27.1z M239.6,43.6c-0.2,1.9-0.4,3.1-0.4,3.6c-0.5,3.9-0.9,6.6-1.3,8.3c-0.5,2.4-1.8,4.5-3.7,6
	c-1.8,1.5-4.1,2.3-6.5,2.2c-4.2,0.3-7.8-2.9-8.1-7.1c0-0.3,0-0.6,0-0.9c0-1.6,0.1-3.2,0.4-4.8c0.2-1.9,0.4-3.1,0.4-3.6
	c0.5-3.7,0.9-6.5,1.3-8.3c0.5-2.4,1.8-4.5,3.7-6c1.8-1.5,4.1-2.3,6.5-2.2c4.2-0.3,7.8,2.9,8.1,7.1c0,0.3,0,0.6,0,0.9
	C239.9,40.4,239.8,42,239.6,43.6z"
    />
    <path
      fill="currentColor"
      d="M258.7,27.7h-2.5c-0.5,0-0.8,0.3-0.9,0.8L250.4,66c-0.1,0.5,0.2,0.8,0.7,0.8h2.6c0.4,0,0.8-0.3,0.9-0.7c0,0,0,0,0,0
	l4.7-37.5C259.4,28,259.2,27.7,258.7,27.7z"
    />
    <path
      fill="currentColor"
      d="M291,29.9c-1.8-1.8-4.2-2.8-7.4-2.8c-2,0-3.9,0.4-5.8,1.2c-1.8,0.8-3.3,2-4.5,3.6c-0.2,0.2-0.3,0.2-0.3-0.2l0.4-3.3
	c0.1-0.5-0.1-0.8-0.6-0.8h-2.5c-0.4,0-0.8,0.3-0.9,0.7c0,0,0,0,0,0L264.6,66c-0.1,0.5,0.1,0.8,0.6,0.8h2.6c0.5,0,0.8-0.3,0.9-0.8
	c0,0,0,0,0,0l3.4-26.9c0.5-2.3,1.7-4.4,3.5-6c1.8-1.5,4-2.3,6.3-2.3c2-0.1,4,0.7,5.4,2.2c1.4,1.6,2.1,3.7,2,5.8c0,0.6,0,1.1-0.1,1.7
	L286.1,66c0,0.2,0,0.4,0.1,0.5c0.2,0.2,0.4,0.2,0.6,0.2h2.5c0.4,0,0.8-0.3,0.9-0.7c0,0,0,0,0,0l3.3-26.2c0.1-1,0.2-1.8,0.2-2.3
	C293.8,34.7,292.9,32,291,29.9z"
    />
    <path
      fill="currentColor"
      d="M121.7,12.6c-1.5-0.8-3.4-0.2-4.3,1.3c-0.8,1.5-0.2,3.4,1.3,4.3c1.5,0.8,3.4,0.2,4.3-1.3c0,0,0,0,0,0
	C123.8,15.3,123.2,13.4,121.7,12.6z"
    />
    <path
      fill="currentColor"
      d="M260.5,12.6c-1.5-0.8-3.4-0.2-4.3,1.3c-0.8,1.5-0.2,3.4,1.3,4.3c1.5,0.8,3.4,0.2,4.3-1.3c0,0,0,0,0,0
	C262.6,15.3,262,13.4,260.5,12.6z"
    />
    <path
      fill="currentColor"
      d="M198.9,27.1c-3.3-0.1-6.6,1-9.3,3.1c-2.6,2-4.4,4.8-5.2,8c-0.7,3-1.2,6-1.6,9.1c-0.4,3-0.6,6-0.7,9.1c-0.1,3,1.1,5.9,3.2,8
	c2.1,2,4.9,3,8.6,3c3.3,0.1,6.6-1,9.2-3c2.6-2,4.4-4.8,5.2-8c0.1-0.3,0.1-0.5,0.2-0.8c0-0.2-0.1-0.4-0.3-0.4c0,0-0.1,0-0.1,0H205
	c-0.2,0-0.4,0.1-0.5,0.4c0,0,0,0.1,0,0.2c-0.5,2.4-1.8,4.5-3.7,6c-1.8,1.5-4.1,2.3-6.5,2.2c-4.2,0.3-7.8-2.9-8.1-7.1
	c0-0.3,0-0.6,0-0.9c0-1.6,0.1-3.2,0.4-4.8c0.2-1.6,0.4-3.1,0.4-3.6c0.5-3.7,0.9-6.5,1.3-8.3c0.5-2.4,1.8-4.5,3.6-6
	c1.8-1.5,4.1-2.3,6.5-2.2c4.2-0.3,7.8,2.9,8.1,7.1c0,0.3,0,0.6,0,0.9v0.1c0,0.3,0.2,0.6,0.6,0.6c0,0,0,0,0,0h3
	c0.3,0,0.5-0.2,0.5-0.4c0,0,0,0,0,0c0-0.3,0-0.6,0-0.9c0.1-3-1-5.9-3.2-8C205.1,28,202.1,26.9,198.9,27.1z"
    />
    <path
      fill="currentColor"
      d="M173.1,30.1c-2.3-2.1-5.4-3.2-8.5-3c-6.8-0.2-12.8,4.4-14.5,11.1c-0.7,3-1.2,6-1.6,9.1c-0.5,3-0.7,6-0.7,9.1
	c-0.1,3,1.1,5.9,3.2,8c2.1,2,4.9,3,8.6,3c3.3,0.1,6.6-1,9.2-3c2.6-2,4.4-4.8,5.2-8c0.1-0.3,0.1-0.5,0.2-0.8c0-0.2-0.1-0.4-0.3-0.4
	c0,0-0.1,0-0.1,0h-3.2c-0.2,0-0.4,0.1-0.5,0.4c0,0.1,0,0.2,0,0.2c-0.5,2.4-1.8,4.5-3.7,6c-1.8,1.5-4.1,2.2-6.5,2.2
	c-4.2,0.3-7.8-2.9-8.1-7.1c0-0.3,0-0.6,0-0.9c0-1.4,0.1-2.8,0.3-4.2l23.1-7.2c0.4-0.1,0.7-0.5,0.7-0.9c0.1-1.2,0.2-3.2,0.2-5.3
	C176.4,35.2,175.2,32.3,173.1,30.1z M172.2,40.9c0,0.2-0.2,0.4-0.4,0.5l-19.1,5.9v-0.1c0.5-3.7,0.9-6.5,1.3-8.3
	c0.5-2.4,1.8-4.5,3.7-6c1.8-1.5,4.1-2.3,6.5-2.2c2.2-0.1,4.3,0.7,5.9,2.3C172.4,35.3,172.4,37.8,172.2,40.9z"
    />
    <path
      fill="currentColor"
      d="M139.1,62.6c0.3-0.2,0.7-0.1,0.8,0.2c0.1,0.1,0.1,0.2,0.1,0.4l-0.3,2.6c0,0.3-0.3,0.6-0.6,0.8c-2.6,1-5.4,1.1-8,0.1
	c-2.9-1.3-3.7-4.2-3.3-7.8l3.4-27.5l0.5-4l1.1-8.8c0-0.4,0.4-0.8,0.8-0.8c0,0,0,0,0.1,0h2.5c0.6,0,0.7,0.3,0.6,0.8l-1.5,12.4h8
	c0.5,0,0.7,0.3,0.6,0.8l-0.2,1.8c0,0.2-0.1,0.4-0.2,0.6c-0.2,0.1-0.4,0.2-0.6,0.2h-8l-2.8,22.5c-0.3,2.4-0.6,4.6,0.6,5.8
	C134.4,64.1,137.5,63.4,139.1,62.6z"
    />
  </svg>
);

type DropdownKey = 'useLitecoin' | 'theFoundation' | 'learn';

type DropdownState = Record<DropdownKey, boolean>;

const dropdownKeys: DropdownKey[] = ['useLitecoin', 'learn', 'theFoundation'];

// Configuration for micro-adjustments to menu item spacing
// All values are in rem units unless otherwise specified
type MenuItemSpacing = {
  marginLeft?: number; // in rem
  marginRight?: number; // in rem (for dropdown items)
  marginTop?: number; // in rem
  marginBottom?: number; // in rem
  marginRightOffset?: number; // Additional offset applied to scaledMargin (in px, for regular items)
  className?: string; // Additional className adjustments
};

type MenuSpacingConfig = {
  dropdowns: Record<DropdownKey, MenuItemSpacing>;
  regular: {
    projects: MenuItemSpacing;
    news: MenuItemSpacing;
    events: MenuItemSpacing;
    shop: MenuItemSpacing;
    explorer: MenuItemSpacing;
  };
};

/**
 * Centralized spacing configuration for menu items
 * 
 * To make micro-adjustments:
 * - Dropdown items: Adjust marginLeft, marginRight, marginTop (in rem units)
 * - Regular items: Adjust marginLeft, marginTop, marginBottom (in rem units) and marginRightOffset (in px, added to scaledMargin)
 * - Tip: Adjust by 0.05-0.1rem increments for fine-tuning
 * - Negative values are allowed for precise positioning
 */
const menuSpacingConfig: MenuSpacingConfig = {
  dropdowns: {
    useLitecoin: {
      marginRight: 1.8,
      marginTop: -0.050,
      className: '',
    },
    theFoundation: {
      marginRight: 1,
      marginTop: 0,
      marginLeft: 0,
      className: '',
    },
    learn: {
      marginRight: 1.65,
      marginTop: -0.050,
      className: '',
    },
  },
  regular: {
    projects: {
      // marginLeft: 1,
      marginTop: .95,
      marginBottom: 0.95,
      marginRightOffset: 15,
      className: '',
    },
    news: {
      marginLeft: 0.6,
      marginTop: .95,
      marginBottom: 0.95,
      marginRightOffset: 1,
      className: '',
    },
    events: {
      marginLeft: 0.8,
      marginTop: .95,
      marginBottom: 0.95,
      marginRightOffset: 0.5,
      className: '',
    },
    shop: {
      marginLeft: 0.8,
      marginTop: .95,
      marginBottom: 0.95,
      marginRightOffset: 0.8,
      className: '',
    },
    explorer: {
      marginLeft: 0.8,
      marginTop: .95,
      marginBottom: 0.95,
      marginRightOffset: 1,
      className: '',
    },
  },
};

const Navigation = () => {
  // Get scroll position from context (for ChatWindow) or window (for other pages)
  const { scrollPosition: contextScrollPosition } = useScrollContext();
  const [windowScrollPosition, setWindowScrollPosition] = useState(0);
  const [dropdownOpen, setDropdownOpen] = useState<DropdownState>({
    useLitecoin: false,
    theFoundation: false,
    learn: false,
  });
  const [mobileDropdownOpen, setMobileDropdownOpen] = useState<DropdownState>({
    useLitecoin: false,
    theFoundation: false,
    learn: false,
  });
  const [isMobile, setIsMobile] = useState(false);
  const [navShow, setNavShow] = useState(false);

  const useLitecoinRef = useRef<HTMLLIElement | null>(null);
  const theFoundationRef = useRef<HTMLLIElement | null>(null);
  const learnRef = useRef<HTMLLIElement | null>(null);

  // Use the maximum of context scroll (from ChatWindow) and window scroll (from other pages)
  // This ensures we use the correct scroll source depending on which page we're on
  const scrollPosition = Math.max(contextScrollPosition, windowScrollPosition);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 992);
    };

    const handleScroll = () => {
      setWindowScrollPosition(window.scrollY);
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll);
    handleResize();
    // Initialize window scroll position
    setWindowScrollPosition(window.scrollY);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  const toggleDropdown = (menu: DropdownKey) => {
    setDropdownOpen((prev) => {
      const nextState: DropdownState = {
        useLitecoin: false,
        theFoundation: false,
        learn: false,
      };
      nextState[menu] = !prev[menu];
      return nextState;
    });
  };

  const toggleMobileDropdown = (menu: DropdownKey) => {
    setMobileDropdownOpen((prevState) => ({
      ...prevState,
      [menu]: !prevState[menu],
    }));
  };

  const handleClickOutside = (event: MouseEvent) => {
  const targets: Array<[RefObject<HTMLLIElement | null>, DropdownKey]> = [
      [useLitecoinRef, 'useLitecoin'],
      [theFoundationRef, 'theFoundation'],
      [learnRef, 'learn'],
    ];

    targets.forEach(([ref, key]) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setDropdownOpen((prev) => ({ ...prev, [key]: false }));
      }
    });
  };

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const onToggleNav = () => {
    setNavShow((status) => {
      if (status) {
        document.body.style.overflow = 'auto';
      } else {
        document.body.style.overflow = 'hidden';
      }
      return !status;
    });
  };

  const maxScrollHeight = 225;
  const minHeight = 80;
  const initialHeight = 80;
  const bgOpacity = Math.min(scrollPosition / maxScrollHeight, 1);
  const baseHeaderHeight = isMobile ? initialHeight - 10 : initialHeight;
  const minHeaderHeight = isMobile ? minHeight - 10 : minHeight;
  const headerHeight = Math.max(
    baseHeaderHeight -
      (scrollPosition / maxScrollHeight) * (baseHeaderHeight - minHeaderHeight),
    minHeaderHeight,
  );
  const baseLogoSize = isMobile ? 130 : 142;
  const minLogoSize = 124;
  const logoSize = Math.max(
    baseLogoSize -
      (scrollPosition / maxScrollHeight) * (baseLogoSize - minLogoSize),
    minLogoSize,
  );
  const baseFontSize = 16;
  const scaledFontSize = Math.max(
    baseFontSize - (scrollPosition / maxScrollHeight) * 2,
    14.25,
  );
  const baseMargin = 14;
  const scaledMargin = Math.max(
    baseMargin - (scrollPosition / maxScrollHeight) * 4,
    12,
  );

  const interpolateColor = (startColor: string, endColor: string, factor: number) => {
    const startComponents = startColor.slice(1).match(/.{2}/g) ?? [];
    const endComponents = endColor.slice(1).match(/.{2}/g) ?? [];

    const result = startComponents.map((hex, index) => {
      const startValue = parseInt(hex, 16);
      const endValue = parseInt(endComponents[index] ?? hex, 16);
      const interpolated = Math.round(startValue * (1 - factor) + endValue * factor);
      return interpolated.toString(16).padStart(2, '0');
    });

    return `#${result.join('')}`;
  };

  const fontColor = interpolateColor('#222222', '#C6D3D6', bgOpacity);
  const dropdownBgColor = interpolateColor('#c6d3d6', '#222222', bgOpacity);
  const dropdownTextColor = interpolateColor('#222222', '#C6D3D6', bgOpacity);
  const hamburgerColor = interpolateColor('#222222', '#ffffff', bgOpacity);
  const mobileMenuTextColor = interpolateColor('#222222', '#C5D3D6', bgOpacity);
  const socialIconTextColor = interpolateColor('#222222', '#ffffff', bgOpacity);
  const logoColor = bgOpacity < 0.5 ? '#000000' : '#ffffff';

  const dropdownRefs: Record<DropdownKey, RefObject<HTMLLIElement | null>> = {
    useLitecoin: useLitecoinRef,
    theFoundation: theFoundationRef,
    learn: learnRef,
  };

  // Helper function to render dropdown menu items with configurable spacing
  const renderDropdownMenuItem = (key: DropdownKey) => {
    const spacing = menuSpacingConfig.dropdowns[key];
    const spacingStyle: CSSProperties = {};
    if (spacing.marginLeft !== undefined) spacingStyle.marginLeft = `${spacing.marginLeft}rem`;
    if (spacing.marginRight !== undefined) spacingStyle.marginRight = `${spacing.marginRight}rem`;
    if (spacing.marginTop !== undefined) spacingStyle.marginTop = `${spacing.marginTop}rem`;
    if (spacing.marginBottom !== undefined) spacingStyle.marginBottom = `${spacing.marginBottom}rem`;

    const labels: Record<DropdownKey, string> = {
      useLitecoin: 'Use Litecoin',
      theFoundation: 'The Foundation',
      learn: 'Learn',
    };

    const dropdownWidths: Record<DropdownKey, string> = {
      useLitecoin: '113.63px',
      learn: '165px',
      theFoundation: '140px',
    };

    return (
      <li
        key={key}
        className={`relative flex items-center !font-[500] ${spacing.className || ''}`}
        style={spacingStyle}
        ref={dropdownRefs[key]}
      >
        <button
          className="flex items-center tracking-[-0.01em]"
          onClick={() => toggleDropdown(key)}
          aria-expanded={dropdownOpen[key]}
          aria-haspopup="true"
          style={{ color: fontColor, fontSize: '1rem' }}
          type="button"
        >
          {labels[key]}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className={`ml-2 h-4 w-4${dropdownOpen[key] ? ' rotate-180' : ''}`}
            style={{
              transformOrigin: 'center',
            }}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={3.25}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>
        <ul
          className={`w-[var(--dropdown-width, 180px)] absolute left-0 top-full mt-3 rounded-2xl ${
            dropdownOpen[key] ? 'dropdown-enter-active' : 'dropdown-exit-active'
          }`}
          style={
            {
              backgroundColor: dropdownBgColor,
              color: dropdownTextColor,
              fontSize: `${scaledFontSize}px`,
              visibility: dropdownOpen[key] ? 'visible' : 'hidden',
              width: dropdownWidths[key],
              '--dropdown-width': dropdownWidths[key],
            } as CSSProperties & { [customProperty: string]: string }
          }
        >
          {key === 'useLitecoin' && (
            <>
              <li className="ml-2 mt-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/buy">Buy</a>
              </li>
              <li className="ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/spend">Spend</a>
              </li>
              <li className="ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/store">Store</a>
              </li>
              <li className="mb-2 ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/for-business">Business</a>
              </li>
            </>
          )}
          {key === 'learn' && (
            <>
              <li className="ml-2 mt-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/learningcenter">Learning Center</a>
              </li>
              <li className="mb-2 ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/resources">Resources</a>
              </li>
              <li className="mb-2 ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/chat">Chat</a>
              </li>
            </>
          )}
          {key === 'theFoundation' && (
            <>
              <li className="ml-2 mt-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/litecoin-foundation">About</a>
              </li>
              <li className="ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/donate">Donate</a>
              </li>
              <li className="ml-2 p-2 pl-4 text-left">
                <a href="https://litecoin.com/litecoin-foundation#contact">Contact</a>
              </li>
              <li className="mb-2 ml-2 p-2 pl-4 text-left">w
                <a href="https://litecoin.com/financials">Financials</a>
              </li>
            </>
          )}
        </ul>
      </li>
    );
  };

  // Helper function to render regular menu items with configurable spacing
  const renderRegularMenuItem = (
    spacing: MenuItemSpacing,
    href: string,
    label: string,
    target?: string,
    rel?: string,
  ) => {
    return (
      <li
        className={`text-md font-[500] ${spacing.className || ''}`}
        style={{
          color: fontColor,
          letterSpacing: '-0.2px',
          fontSize: `${scaledFontSize}px`,
          marginLeft: spacing.marginLeft !== undefined ? `${spacing.marginLeft}rem` : undefined,
          marginTop: spacing.marginTop !== undefined ? `${spacing.marginTop}rem` : undefined,
          marginBottom: spacing.marginBottom !== undefined ? `${spacing.marginBottom}rem` : undefined,
          marginRight: `${scaledMargin + (spacing.marginRightOffset || 0)}px`,
        }}
      >
        <a href={href} target={target} rel={rel}>
          {label}
        </a>
      </li>
    );
  };

  return (
    <>
      <header
        style={{
          backgroundColor: `rgba(34, 34, 34, ${bgOpacity})`,
          height: `${headerHeight}px`,
          fontFamily:
            'system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Oxygen, Ubuntu, Cantarell, Fira Sans, Droid Sans, Helvetica Neue, sans-serif',
        }}
        className="fixed left-0 right-0 top-0 z-[60] flex items-center justify-between"
      >
        <div className="mx-auto flex h-full w-[1300px] max-w-[90%] items-center justify-between">
          <div className="relative flex h-full items-center pb-1">
            <a href="https://litecoin.com" aria-label={siteMetadata.headerTitle}>
              <div
                className={`relative ${isMobile ? 'ml-2' : 'ml-1'}  mt-[3px]`}
                style={{
                  height: `${logoSize}px`,
                  width: `${logoSize}px`,
                  transform: 'translateY(-0.5px)',
                  color: logoColor,
                  transition: 'color 0.3s ease-in-out',
                }}
              >
                <LitecoinLogo width={logoSize} height={logoSize} />
              </div>
            </a>
          </div>
          <nav>
            {isMobile ? (
              <div
                className={`nav-toggle mt-[-10px] ${navShow ? 'open' : ''}`}
                onClick={onToggleNav}
                onKeyPress={onToggleNav}
                aria-label="menu"
                role="button"
                tabIndex={0}
              >
                <span className="bar" style={{ backgroundColor: hamburgerColor }}></span>
                <span className="bar" style={{ backgroundColor: hamburgerColor }}></span>
                <span className="bar" style={{ backgroundColor: hamburgerColor }}></span>
              </div>
            ) : (
              <ul className="flex flex-row">
                {/* Order: Use Litecoin, Learn, Projects, The Foundation, News, Events, Shop, Explorer */}
                {renderDropdownMenuItem('useLitecoin')}
                {renderDropdownMenuItem('learn')}
                {renderRegularMenuItem(
                  menuSpacingConfig.regular.projects,
                  'https://litecoin.com/projects',
                  'Projects',
                )}
                {renderDropdownMenuItem('theFoundation')}
                {renderRegularMenuItem(
                  menuSpacingConfig.regular.news,
                  'https://litecoin.com/news',
                  'News',
                )}
                {renderRegularMenuItem(
                  menuSpacingConfig.regular.events,
                  'https://litecoin.com/events',
                  'Events',
                )}
                {renderRegularMenuItem(
                  menuSpacingConfig.regular.shop,
                  'https://shop.litecoin.com',
                  'Shop',
                )}
                {renderRegularMenuItem(
                  menuSpacingConfig.regular.explorer,
                  'https://litecoinspace.org/',
                  'Explorer',
                  '_blank',
                  'noreferrer',
                )}
              </ul>
            )}
          </nav>
        </div>
      </header>

      <div
        className={`fixed bottom-0 left-0 right-0 top-0 z-50 min-w-full transform overflow-y-auto pt-20 duration-300 ease-in md:clear-left ${
          navShow ? 'translate-x-0' : 'translate-x-[105%]'
        }`}
        style={{
          backgroundColor: interpolateColor('#C5D3D6', '#222222', bgOpacity),
        }}
      >
        <div className="flex flex-col gap-x-6">
          <nav className="mt-10 min-h-full">
            {[
              { title: 'Use Litecoin', dropdown: true },
              { title: 'Learn', dropdown: true },
              { title: 'Projects', link: 'https://litecoin.com/projects' },
              { title: 'The Foundation', dropdown: true },
              { title: 'News', link: 'https://litecoin.com/news' },
              { title: 'Events', link: 'https://litecoin.com/events' },
              { title: 'Shop', link: 'https://shop.litecoin.com' },
              { title: 'Explorer', link: 'https://litecoinspace.org/' },
            ].map((item) => {
              const itemKey = item.title.replace(' ', '').toLowerCase() as DropdownKey | string;
              const dropdownKey = dropdownKeys.find(
                (key) => key.toLowerCase() === itemKey,
              ) as DropdownKey | undefined;

              return (
                <div key={item.title} className="px-10 py-2 short:py-0.5">
                  {item.dropdown && dropdownKey ? (
                    <>
                      <button
                        onClick={() => toggleMobileDropdown(dropdownKey)}
                        className="m-0 flex w-full items-center justify-between pl-0 pr-0 text-left font-space-grotesk text-[2.1rem] font-semibold"
                        style={{ color: mobileMenuTextColor }}
                        aria-expanded={mobileDropdownOpen[dropdownKey]}
                        aria-haspopup="true"
                        type="button"
                      >
                        {item.title}
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-10 w-10 transition-transform duration-200"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          style={{
                            transform: `translateY(-0.5px) ${
                              mobileDropdownOpen[dropdownKey] ? 'rotate(180deg)' : ''
                            }`,
                          }}
                        >
                          <path
                            strokeLinecap="butt"
                            strokeLinejoin="miter"
                            strokeWidth={2.5}
                            d="M19 9l-6.75 6.75-6.75-6.75"
                          />
                        </svg>
                      </button>
                      {mobileDropdownOpen[dropdownKey] ? (
                        <ul
                          className="pl-6 font-space-grotesk text-[2.1rem] font-semibold"
                          style={{ color: mobileMenuTextColor }}
                        >
                          {dropdownKey === 'useLitecoin' && (
                            <>
                              <li className="py-1">
                                <a href="https://litecoin.com/buy">Buy</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/spend">Spend</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/store">Store</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/for-business">Business</a>
                              </li>
                            </>
                          )}
                          {dropdownKey === 'theFoundation' && (
                            <>
                              <li className="py-1">
                                <a href="https://litecoin.com/litecoin-foundation">About</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/litecoin-foundation#contact">
                                  Contact
                                </a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/donate">Donate</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/financials">Financials</a>
                              </li>
                            </>
                          )}
                          {dropdownKey === 'learn' && (
                            <>
                              <li className="py-1">
                                <a href="https://litecoin.com/what-is-litecoin">What Is Litecoin</a>
                              </li>
                              <li className="py-1">
                                <a href="https://litecoin.com/resources">Resources</a>
                              </li>
                            </>
                          )}
                        </ul>
                      ) : null}
                    </>
                  ) : (
                    <a
                      href={item.link}
                      className="flex w-full items-center justify-between text-left font-space-grotesk text-[2.1rem] font-semibold"
                      style={{ color: mobileMenuTextColor }}
                    >
                      {item.title}
                    </a>
                  )}
                </div>
              );
            })}
          </nav>
          <HorizontalSocialIcons mobileMenuTextColor={socialIconTextColor} />
        </div>
      </div>
      <style jsx>{`
        :root {
          --menu-item-margin: ${scaledMargin - 1.9}px;
          --dropdown-width: 180px;
        }

        .nav-toggle {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          height: 28px;
          width: 45px;
        }

        .nav-toggle .bar {
          height: 4px;
          width: 100%;
          background-color: ${hamburgerColor};
          transition: transform 300ms ease-in-out, width 300ms ease-in-out;
        }

        .nav-toggle:not(.open) .bar {
          transition: none;
        }

        .nav-toggle:hover {
          cursor: pointer;
        }

        .nav-toggle.open .bar:nth-of-type(1) {
          transform: rotate(45deg) translateY(-4px);
          transform-origin: top left;
          width: 44px;
        }

        .nav-toggle.open .bar:nth-of-type(2) {
          transform-origin: center;
          width: 0;
        }

        .nav-toggle.open .bar:nth-of-type(3) {
          transform: rotate(-45deg) translateY(4px);
          transform-origin: bottom left;
          width: 44px;
        }

        .dropdown-enter-active,
        .dropdown-exit-active {
          transition: opacity 200ms ease-in-out, visibility 200ms ease-in-out;
        }

        .dropdown-enter-active {
          opacity: 1;
          visibility: visible;
        }

        .dropdown-exit-active {
          opacity: 0;
          visibility: hidden;
        }

        svg {
          transition: transform 0ms ease-in-out;
        }

        ul > li > ul {
          top: 100%;
          left: 0;
          width: var(--dropdown-width);
        }

        ul.flex > li {
          margin-right: var(--menu-item-margin);
        }

        @media (max-width: 991px) {
        }
      `}</style>
    </>
  );
};

export default Navigation;

