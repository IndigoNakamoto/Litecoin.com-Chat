import React, { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef, useLayoutEffect } from "react";

interface ChatWindowProps {
  children: React.ReactNode;
  shouldScrollToBottom?: boolean;
  onScrollChange?: (scrollTop: number) => void;
  pinnedMessageId?: string | null;
}

export interface ChatWindowRef {
  scrollToElement: (element: HTMLElement | null) => void;
  scrollToTop: () => void;
}

const ChatWindow = forwardRef<ChatWindowRef, ChatWindowProps>(
  ({ children, shouldScrollToBottom = false, onScrollChange, pinnedMessageId = null }, ref) => {
    const scrollRef = useRef<HTMLDivElement>(null);
    const spacerRef = useRef<HTMLDivElement>(null);
    const userMessageRef = useRef<HTMLElement | null>(null);
    const aiResponseRef = useRef<HTMLElement | null>(null);
    const [isUserScrolling, setIsUserScrolling] = useState(false);
    const [lastScrollTop, setLastScrollTop] = useState(0);
    const isProgrammaticScrollRef = useRef(false);

    // Expose scroll methods via ref
    useImperativeHandle(ref, () => ({
      scrollToElement: (element: HTMLElement | null) => {
        if (element && scrollRef.current) {
          const container = scrollRef.current;
          
          // Scroll function that recalculates position right before scrolling
          const performScroll = () => {
            // Calculate element's position relative to container using getBoundingClientRect
            const containerRect = container.getBoundingClientRect();
            const elementRect = element.getBoundingClientRect();
            
            // Get computed styles to account for padding
            const containerStyles = window.getComputedStyle(container);
            const paddingTop = parseFloat(containerStyles.paddingTop) || 0;
            
            // The element's position relative to the container's visible top edge
            const elementOffsetFromContainerTop = elementRect.top - containerRect.top;
            
            // The element's absolute position in the scrollable content
            // This is where the element actually is in the scrollable content
            const absoluteElementPosition = elementOffsetFromContainerTop + container.scrollTop;
            
            // To position the element at the top of the content area (after padding),
            // we need to scroll so that the element's absolute position minus padding equals scrollTop
            // So: scrollTop = absoluteElementPosition - paddingTop
            const targetScroll = absoluteElementPosition - paddingTop;
            
            // Check if container can actually scroll
            const maxScroll = container.scrollHeight - container.clientHeight;
            const clampedScroll = Math.min(Math.max(0, targetScroll), maxScroll);
            
            // Set flag to prevent scroll handler from interfering
            isProgrammaticScrollRef.current = true;
            
            // Scroll to position the element at the top of the content area (after padding)
            container.scrollTop = clampedScroll;
            
            // Verify scroll worked and retry if needed
            setTimeout(() => {
              const actualScrollTop = container.scrollTop;
              
              // Check where the element actually ended up
              const newElementRect = element.getBoundingClientRect();
              const newContainerRect = container.getBoundingClientRect();
              const finalOffset = newElementRect.top - newContainerRect.top;
              const offsetFromTarget = Math.abs(finalOffset - paddingTop);
              
              // If element is not at the top (accounting for padding), retry with corrected calculation
              if (offsetFromTarget > 2 && container.scrollHeight > container.clientHeight) {
                // Recalculate: current offset + current scroll = absolute position
                // We want: scrollTop = absolutePosition - paddingTop
                const retryAbsolute = finalOffset + actualScrollTop;
                const retryTarget = retryAbsolute - paddingTop;
                const retryClamped = Math.min(Math.max(0, retryTarget), maxScroll);
                container.scrollTop = retryClamped;
              }
              
              isProgrammaticScrollRef.current = false;
            }, 100);
          };
          
          // Wait for layout to be ready, then scroll
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              setTimeout(performScroll, 100);
            });
          });
        }
      },
      scrollToTop: () => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = 0;
        }
      },
    }));

    // Intelligent auto-scroll logic
    const scrollToBottom = useCallback(() => {
      if (scrollRef.current && !isUserScrolling) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, [isUserScrolling]);

  // Handle scroll events to detect user interaction
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    
    // Always notify parent component of scroll position change (for navigation updates)
    if (onScrollChange) {
      onScrollChange(scrollTop);
    }
    
    // Only detect user interaction if not programmatic scrolling
    if (isProgrammaticScrollRef.current) {
      return;
    }

    const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10; // 10px tolerance

    // If user scrolls up, mark as user scrolling
    if (scrollTop < lastScrollTop && !isAtBottom) {
      setIsUserScrolling(true);
    }
    // If user scrolls back to bottom, resume auto-scroll
    else if (isAtBottom) {
      setIsUserScrolling(false);
    }

    setLastScrollTop(scrollTop);
  }, [lastScrollTop, onScrollChange]);

  // Auto-scroll when content changes (if not user scrolling)
  useEffect(() => {
    if (shouldScrollToBottom) {
      // Small delay to ensure DOM has updated
      const timeoutId = setTimeout(scrollToBottom, 50);
      return () => clearTimeout(timeoutId);
    }
  }, [shouldScrollToBottom, children, scrollToBottom]);

  // Attach scroll listener
  useEffect(() => {
    const scrollElement = scrollRef.current;
    if (scrollElement) {
      scrollElement.addEventListener('scroll', handleScroll, { passive: true });
      return () => scrollElement.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll]);

  // Find and track user message and AI response elements
  useEffect(() => {
    if (pinnedMessageId) {
      // Use requestAnimationFrame to ensure DOM is updated
      requestAnimationFrame(() => {
        const userElement = document.getElementById(pinnedMessageId);
        userMessageRef.current = userElement;
        
        // Find the next sibling element which should be the AI response
        // This could be a StreamingMessage or a completed Message component
        if (userElement) {
          let nextSibling = userElement.nextElementSibling;
          // Skip any non-content elements (like loaders, etc.)
          while (nextSibling && nextSibling.classList.contains('hidden')) {
            nextSibling = nextSibling.nextElementSibling;
          }
          aiResponseRef.current = nextSibling as HTMLElement || null;
        } else {
          aiResponseRef.current = null;
        }
      });
    } else {
      userMessageRef.current = null;
      aiResponseRef.current = null;
    }
  }, [pinnedMessageId, children]);

  // Calculate spacer height to prevent reverse scrolling
  // The spacer maintains constant scrollable height so the scroll position doesn't shift
  // as the AI response grows, but users can still scroll up naturally
  useLayoutEffect(() => {
    if (!pinnedMessageId || !scrollRef.current || !spacerRef.current) {
      // Reset spacer height when not pinning
      if (spacerRef.current) {
        spacerRef.current.style.height = '0px';
      }
      return;
    }

    const calculateAndApplySpacerHeight = () => {
      const container = scrollRef.current;
      const spacer = spacerRef.current;
      const userMessage = userMessageRef.current;
      const aiResponse = aiResponseRef.current;

      if (!container || !spacer || !userMessage) {
        return;
      }

      // Get container padding to account for it in calculations
      const containerStyles = window.getComputedStyle(container);
      const paddingTop = parseFloat(containerStyles.paddingTop) || 0;
      const paddingBottom = parseFloat(containerStyles.paddingBottom) || 0;

      // Get heights
      const userHeight = userMessage.offsetHeight;
      const aiHeight = aiResponse?.offsetHeight || 0;
      const viewportHeight = container.clientHeight;
      const totalContentHeight = userHeight + aiHeight;

      // Calculate spacer height
      let spacerHeight = 0;
      const isContentShort = totalContentHeight < viewportHeight;
      
      if (isContentShort) {
        // Content is short - maintain viewport height to keep empty space
        spacerHeight = viewportHeight - totalContentHeight - paddingTop - paddingBottom;
        spacerHeight = Math.max(0, spacerHeight);
      } else {
        // Content exceeds viewport - spacer is 0, allow native scrolling
        spacerHeight = 0;
      }

      // Apply spacer height directly to DOM to prevent jitter
      // This maintains constant scrollable height, preventing reverse scrolling
      // but allows users to scroll up naturally
      spacer.style.height = `${spacerHeight}px`;
    };

    // Initial calculation
    calculateAndApplySpacerHeight();

    // Set up ResizeObserver to watch for height changes
    const observers: ResizeObserver[] = [];

    if (userMessageRef.current) {
      const userObserver = new ResizeObserver(() => {
        requestAnimationFrame(() => {
          calculateAndApplySpacerHeight();
        });
      });
      userObserver.observe(userMessageRef.current);
      observers.push(userObserver);
    }

    if (aiResponseRef.current) {
      const aiObserver = new ResizeObserver(() => {
        requestAnimationFrame(() => {
          calculateAndApplySpacerHeight();
        });
      });
      aiObserver.observe(aiResponseRef.current);
      observers.push(aiObserver);
    }

    if (scrollRef.current) {
      const containerObserver = new ResizeObserver(() => {
        requestAnimationFrame(() => {
          calculateAndApplySpacerHeight();
        });
      });
      containerObserver.observe(scrollRef.current);
      observers.push(containerObserver);
    }

    return () => {
      observers.forEach(observer => observer.disconnect());
    };
  }, [pinnedMessageId, children]);

    return (
      <div ref={scrollRef} className="flex flex-col flex-1 min-h-0 mx-4 mt-4 px-4 md:px-16 pt-16 pb-8 overflow-y-auto">
        {children}
        {pinnedMessageId && (
          <div ref={spacerRef} style={{ height: '0px', flexShrink: 0 }} />
        )}
      </div>
    );
  }
);

ChatWindow.displayName = "ChatWindow";

export default ChatWindow;
