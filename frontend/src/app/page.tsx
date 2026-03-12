"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ChatWindow, { ChatWindowRef } from "@/components/ChatWindow";
import Message from "@/components/Message";
import StreamingMessage from "@/components/StreamingMessage";
import MessageLoader from "@/components/MessageLoader";
import InputBox from "@/components/InputBox";
import SuggestedQuestions from "@/components/SuggestedQuestions";
import { getFingerprintWithChallenge, getFingerprint } from "@/lib/utils/fingerprint";
import { useScrollContext } from "@/contexts/ScrollContext";

interface Message {
  role: "human" | "ai"; // Changed to match backend Pydantic model
  content: string;
  followUpQuestions?: string[];
  status?: "thinking" | "streaming" | "complete" | "error";
  isStreamActive?: boolean;
  id?: string;
  // Retry information for challenge errors
  retryInfo?: {
    retryAfterSeconds: number;
    banExpiresAt?: number;
    violationCount?: number;
    errorType: string;
    originalMessage?: string;
  };
}

interface UsageStatus {
  status: string;
  warning_level: "error" | "warning" | "info" | null;
  // Note: daily_percentage and hourly_percentage removed for security - not returned from stream
}

interface ErrorResponseData {
  detail?: {
    error?: string;
    message?: string;
    retry_after_seconds?: number;
    ban_expires_at?: number;
    violation_count?: number;
  };
  error?: string;
  message?: string;
  retry_after_seconds?: number;
  ban_expires_at?: number;
  violation_count?: number;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState<Message | null>(null);
  const [usageWarning, setUsageWarning] = useState<UsageStatus | null>(null);
  // Fingerprint state is kept for background refresh, but we fetch fresh before each request
  const [_fingerprint, setFingerprint] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const streamReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const activeStreamIdRef = useRef(0);
  const chatWindowRef = useRef<ChatWindowRef>(null);
  const lastUserMessageIdRef = useRef<string | null>(null);
  const { setScrollPosition, setPinnedMessageId, resetPinningContext, pinnedMessageId } = useScrollContext();
  
  const getChatApiBaseUrl = useCallback(() => {
    if (typeof window !== "undefined") {
      return `${window.location.origin}/chat`;
    }
    return process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  }, []);
  
  
  const clearConversation = useCallback(() => {
    // Invalidate any in-flight stream loop so it stops updating state.
    activeStreamIdRef.current += 1;

    // Best-effort: cancel any active stream reader.
    try {
      streamReaderRef.current?.cancel();
    } catch (e) {
      console.debug("Failed to cancel stream reader (safe to ignore):", e);
    } finally {
      streamReaderRef.current = null;
    }

    // Best-effort: close any lingering EventSource (legacy).
    try {
      eventSourceRef.current?.close();
    } catch (e) {
      console.debug("Failed to close EventSource (safe to ignore):", e);
    } finally {
      eventSourceRef.current = null;
    }

    // Reset UI state back to the "Get started with Litecoin" landing experience.
    setIsLoading(false);
    setStreamingMessage(null);
    setMessages([]);
    setUsageWarning(null);
    lastUserMessageIdRef.current = null;

    resetPinningContext();
    setScrollPosition(0);
    setPinnedMessageId(null);
  }, [resetPinningContext, setPinnedMessageId, setScrollPosition]);

  // Helper function to extract base fingerprint hash from fingerprint string
  const extractBaseFingerprint = (fp: string | null): string | null => {
    if (!fp) return null;
    // If fingerprint is in format fp:challenge:hash, extract the hash part
    if (fp.startsWith("fp:") && fp.split(":").length === 3) {
      const parts = fp.split(":");
      return parts[2]; // Return just the hash part
    }
    // Otherwise, assume it's already a base hash
    return fp;
  };

  // Helper function to extract retry seconds from error message
  // Handles formats like "Please wait 8 seconds before trying again." or "try again in 30 seconds."
  const extractRetrySecondsFromMessage = (message: string): number | null => {
    if (!message) return null;
    
    // Try to match patterns like "wait X seconds" or "in X seconds"
    const patterns = [
      /wait\s+(\d+)\s+seconds?/i,
      /in\s+(\d+)\s+seconds?/i,
      /(\d+)\s+seconds?/i, // Fallback: just find a number followed by "seconds"
    ];
    
    for (const pattern of patterns) {
      const match = message.match(pattern);
      if (match && match[1]) {
        const seconds = parseInt(match[1], 10);
        if (!isNaN(seconds) && seconds > 0) {
          return seconds;
        }
      }
    }
    
    return null;
  };

  // Helper function to ensure we have a fresh challenge and fingerprint
  const ensureFreshFingerprint = async (): Promise<string | null> => {
    // Extract base fingerprint from current state (removing challenge prefix if present)
    let baseFp = extractBaseFingerprint(_fingerprint);
    if (!baseFp) {
      // Generate a base fingerprint immediately if state is not yet ready
      console.debug("Generated base fingerprint for challenge request (state was null)");
      baseFp = await getFingerprint();
    }
    
    try {
      const backendUrl = getChatApiBaseUrl();
      
      // Always send base fingerprint in X-Fingerprint header so backend uses hash instead of IP
      const headers: Record<string, string> = {};
      if (baseFp) {
        headers["X-Fingerprint"] = baseFp;
      }
      const response = await fetch(`${backendUrl}/api/v1/auth/challenge`, {
        headers,
      });
      
      if (response.ok) {
        const data = await response.json();
        const challengeId = data.challenge;
        
        if (challengeId && challengeId !== "disabled") {
          // Generate fingerprint with challenge using the same base hash we sent to the challenge endpoint
          const fp = await getFingerprintWithChallenge(challengeId, baseFp);
          setFingerprint(fp);
          return fp;
        } else {
          // Challenge disabled, generate fingerprint without challenge (backward compatibility)
          const fp = baseFp || await getFingerprint();
          setFingerprint(fp);
          return fp;
        }
      } else if (response.status === 429) {
        // Rate limited - extract error message and retry info from response
        console.debug("Received 429 status from challenge endpoint, parsing error response...");
        let errorData: ErrorResponseData | null = null;
        let _parseError: unknown = null;
        
        try {
          const text = await response.text();
          console.debug("Challenge error response text:", text);
          
          // Try to parse as JSON
          try {
            errorData = JSON.parse(text) as ErrorResponseData;
            console.debug("Challenge error response parsed JSON:", errorData);
          } catch (jsonError) {
            console.warn("Failed to parse error response as JSON:", jsonError);
            _parseError = jsonError;
          }
        } catch (textError) {
          console.warn("Failed to read error response text:", textError);
          _parseError = textError;
        }
        
        // FastAPI wraps errors in 'detail', but the response might be at top level too
        // Check multiple possible locations for error data
        const detail = errorData?.detail || errorData;
        const errorType = detail?.error || errorData?.error;
        const errorMessage = detail?.message || errorData?.message || "Too many requests. Please wait before trying again.";
        
        console.debug("Parsed error details:", {
          errorType,
          errorMessage,
          errorData,
          detail,
          hasDetail: !!errorData?.detail,
        });
        
        // Check if it's a too_many_challenges error with retry info
        if (errorType === "too_many_challenges") {
          // Extract retry info - check detail first, then top level, with fallbacks
          const retryAfterSeconds = detail?.retry_after_seconds ?? errorData?.retry_after_seconds ?? 0;
          const banExpiresAt = detail?.ban_expires_at ?? errorData?.ban_expires_at;
          const violationCount = detail?.violation_count ?? errorData?.violation_count ?? 0;
          
          console.debug("Extracted retry info from error response:", {
            retryAfterSeconds,
            banExpiresAt,
            violationCount,
            banExpiresAtType: typeof banExpiresAt,
            errorDataStructure: {
              hasDetail: !!errorData?.detail,
              topLevelError: errorData?.error,
              detailError: detail?.error,
            }
          });
          
          // Ensure banExpiresAt is a number if present
          let parsedBanExpiresAt: number | undefined = undefined;
          if (banExpiresAt !== null && banExpiresAt !== undefined) {
            if (typeof banExpiresAt === 'number') {
              parsedBanExpiresAt = banExpiresAt;
            } else {
              const parsed = parseInt(String(banExpiresAt), 10);
              if (!isNaN(parsed)) {
                parsedBanExpiresAt = parsed;
              }
            }
          }
          
          const retryInfo = {
            retryAfterSeconds: Math.max(0, retryAfterSeconds || 0),
            banExpiresAt: parsedBanExpiresAt,
            violationCount: Math.max(0, violationCount || 0),
            errorType: "too_many_challenges",
          };
          
          console.debug("Created retryInfo object:", retryInfo);
          
          // Throw error with retry info attached
          const error = new Error(errorMessage) as Error & { retryInfo?: typeof retryInfo };
          error.retryInfo = retryInfo;
          console.debug("Throwing error with retryInfo:", { message: error.message, retryInfo: error.retryInfo });
          throw error;
        } else {
          // Not a too_many_challenges error, but still rate limited
          console.debug("Rate limited but not too_many_challenges error type:", errorType);
          throw new Error(errorMessage);
        }
      } else {
        // Other error - fallback to fingerprint without challenge (backward compatibility)
        console.debug("Challenge fetch failed with status:", response.status);
        const fp = baseFp || await getFingerprint();
        setFingerprint(fp);
        return fp;
      }
    } catch (error) {
      // If it's a rate limit error with retryInfo, re-throw it
      if (error instanceof Error) {
        interface RetryInfo {
          retryAfterSeconds: number;
          banExpiresAt?: number;
          violationCount?: number;
          errorType: string;
          originalMessage?: string;
        }
        const errorWithRetry = error as Error & { retryInfo?: RetryInfo };
        if (errorWithRetry.retryInfo || error.message.includes("Rate limited") || error.message.includes("Too many")) {
          console.debug("Re-throwing rate limit error with retryInfo:", {
            message: error.message,
            hasRetryInfo: !!errorWithRetry.retryInfo,
            retryInfo: errorWithRetry.retryInfo,
          });
          throw error;
        }
      }
      // Other errors - fallback to fingerprint without challenge (backward compatibility)
      console.debug("Failed to fetch challenge (non-rate-limit error):", error);
      const fp = baseFp || await getFingerprint();
      setFingerprint(fp);
      return fp;
    }
  };

  const MAX_QUERY_LENGTH = 400;
  
  // Fetch challenge and generate fingerprint on mount
  useEffect(() => {
    const fetchChallengeAndGenerateFingerprint = async () => {
      // Extract base fingerprint (will be null on first mount)
      let baseFp = extractBaseFingerprint(_fingerprint);
      if (!baseFp) {
        // Generate a base fingerprint immediately if state is not yet ready
        console.debug("Generated base fingerprint for challenge request on mount (state was null)");
        baseFp = await getFingerprint();
      }
      
      try {
        const backendUrl = getChatApiBaseUrl();
        
        // Always send base fingerprint in X-Fingerprint header so backend uses hash instead of IP
        const headers: Record<string, string> = {};
        if (baseFp) {
          headers["X-Fingerprint"] = baseFp;
        }
        
        const response = await fetch(`${backendUrl}/api/v1/auth/challenge`, {
          headers,
        });
        
        if (response.ok) {
          const data = await response.json();
          const challengeId = data.challenge;
          
          if (challengeId && challengeId !== "disabled") {
            // Generate fingerprint with challenge using the same base hash we sent to the challenge endpoint
            const fp = await getFingerprintWithChallenge(challengeId, baseFp);
            setFingerprint(fp);
            // Note: No background refresh needed - challenges are fetched on-demand before each request
            // via ensureFreshFingerprint() in handleSendMessage()
          } else {
            // Challenge disabled, generate fingerprint without challenge (backward compatibility)
            const fp = baseFp || await getFingerprint();
            setFingerprint(fp);
          }
        } else {
          // Challenge fetch failed, generate fingerprint without challenge (backward compatibility)
          const fp = baseFp || await getFingerprint();
          setFingerprint(fp);
        }
      } catch (error) {
        console.debug("Failed to fetch challenge:", error);
        // Generate fingerprint without challenge (backward compatibility)
        const fp = baseFp || await getFingerprint();
        setFingerprint(fp);
      }
    };

    fetchChallengeAndGenerateFingerprint();
    // _fingerprint is intentionally excluded - we only want to fetch on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  // Retry handler for failed messages
  const handleRetryMessage = async (messageId: string, originalMessage: string) => {
    // Remove the error message and retry
    setMessages((prevMessages) => {
      // Remove any error messages that came after this user message
      const userMessageIndex = prevMessages.findIndex((msg) => msg.id === messageId);
      if (userMessageIndex >= 0) {
        // Remove the user message and any subsequent messages (error messages)
        return prevMessages.slice(0, userMessageIndex);
      }
      return prevMessages;
    });
    
    // Clear retry info from the message
    setMessages((prevMessages) => {
      const updatedMessages = [...prevMessages];
      const messageIndex = updatedMessages.findIndex((msg) => msg.id === messageId);
      if (messageIndex >= 0) {
        updatedMessages[messageIndex] = {
          ...updatedMessages[messageIndex],
          retryInfo: undefined,
        };
      }
      return updatedMessages;
    });
    
    // Retry sending the message
    await handleSendMessage(originalMessage);
  };

  const handleSendMessage = async (message: string, _metadata?: { fromFeelingLit?: boolean; originalQuestion?: string }) => {
    // Validate message length
    if (message.length > MAX_QUERY_LENGTH) {
      alert(`Message is too long. Maximum length is ${MAX_QUERY_LENGTH} characters. Your message is ${message.length} characters.`);
      return;
    }

    // Trim whitespace
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      return; // Don't send empty messages
    }

    const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newUserMessage: Message = { role: "human", content: trimmedMessage, id: messageId };

    // Reset pinning context for new message
    resetPinningContext();

    // Prepare chat history for the backend - only include complete exchanges
    const chatHistoryForBackend = messages.map(msg => ({
      role: msg.role,
      content: msg.content
    }));

    setMessages((prevMessages) => [...prevMessages, newUserMessage]);
    lastUserMessageIdRef.current = messageId;
    setIsLoading(true);

    // Set pinned message ID and scroll to top
    setPinnedMessageId(messageId);
    
    // Scroll user message to top immediately
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const messageElement = document.getElementById(messageId);
        if (messageElement && chatWindowRef.current) {
          chatWindowRef.current.scrollToElement(messageElement);
        }
      });
    });

    // Initialize streaming message
    const initialStreamingMessage: Message = {
      role: "ai",
      content: "",
      status: "thinking",
      isStreamActive: true
    };
    setStreamingMessage(initialStreamingMessage);

    // Track this stream so we can safely cancel/ignore it if user clears the conversation
    // or starts a newer stream before this one completes.
    activeStreamIdRef.current += 1;
    const streamId = activeStreamIdRef.current;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

    try {
      // Close any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const backendUrl = getChatApiBaseUrl();
      
      // Ensure we have a fresh challenge and fingerprint before each request
      // Challenges are one-time use, so we need a new one for each request
      let currentFingerprint: string | null;
      try {
        console.debug("Fetching fresh challenge and fingerprint...");
        currentFingerprint = await ensureFreshFingerprint();
        console.debug("Successfully obtained fingerprint:", currentFingerprint ? "present" : "null");
      } catch (error) {
        // If challenge fetch failed (e.g., rate limited), handle retry info
        console.debug("Challenge fetch failed, error:", error);
        
        if (error instanceof Error) {
          const errorWithRetry = error as Error & { retryInfo?: { retryAfterSeconds: number; banExpiresAt?: number; violationCount?: number; errorType: string } };
          
          console.debug("Challenge fetch error details:", {
            message: errorWithRetry.message,
            hasRetryInfo: !!errorWithRetry.retryInfo,
            retryInfo: errorWithRetry.retryInfo,
          });
          
          // If it has retry info (too_many_challenges), store it in the user message
          if (errorWithRetry.retryInfo) {
            // Validate retry info has required fields
            const retryInfo = errorWithRetry.retryInfo;
            if (retryInfo.errorType && retryInfo.errorType === "too_many_challenges") {
              const retryInfoToStore = {
                retryAfterSeconds: retryInfo.retryAfterSeconds ?? 0,
                banExpiresAt: retryInfo.banExpiresAt,
                violationCount: retryInfo.violationCount ?? 0,
                errorType: retryInfo.errorType,
                originalMessage: trimmedMessage,
              };
              
              console.debug("Storing retry info in message:", {
                messageId,
                retryInfoToStore,
                trimmedMessageLength: trimmedMessage.length,
              });
              
              // Use functional update to ensure we have the latest state
              setMessages((prevMessages) => {
                const updatedMessages = [...prevMessages];
                // Find the message by ID (should be the last one we just added)
                const messageIndex = updatedMessages.findIndex(msg => msg.id === messageId);
                
                if (messageIndex >= 0) {
                  console.debug(`Found message at index ${messageIndex}, updating with retry info`);
                  updatedMessages[messageIndex] = {
                    ...updatedMessages[messageIndex],
                    retryInfo: retryInfoToStore,
                  };
                  console.debug("Updated message:", {
                    id: updatedMessages[messageIndex].id,
                    role: updatedMessages[messageIndex].role,
                    hasRetryInfo: !!updatedMessages[messageIndex].retryInfo,
                    retryInfo: updatedMessages[messageIndex].retryInfo,
                  });
                } else {
                  console.warn(`Message with id ${messageId} not found in messages array. Available IDs:`, 
                    updatedMessages.map(m => m.id));
                  // Message not found - try to add retryInfo to the last message as fallback
                  if (updatedMessages.length > 0) {
                    const lastIndex = updatedMessages.length - 1;
                    console.debug(`Fallback: updating last message at index ${lastIndex}`);
                    updatedMessages[lastIndex] = {
                      ...updatedMessages[lastIndex],
                      retryInfo: retryInfoToStore,
                    };
                  }
                }
                return updatedMessages;
              });
            } else {
              console.warn("Retry info present but missing required errorType or wrong type:", retryInfo);
            }
          } else {
            console.debug("No retry info in error, treating as generic challenge fetch failure");
          }
          
          // Show error message
          setStreamingMessage({
            role: "ai",
            content: error.message,
            status: "error",
            isStreamActive: false,
          });
          setIsLoading(false);
          return;
        }
        
        // For other errors, fall back to fingerprint without challenge
        console.debug("Error is not an Error instance or doesn't have retry info, falling back to base fingerprint");
        currentFingerprint = await getFingerprint();
      }
      
      // Prepare headers with fingerprint if available
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      
      if (currentFingerprint) {
        headers["X-Fingerprint"] = currentFingerprint;
      }
      
      let response = await fetch(`${backendUrl}/api/v1/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ query: trimmedMessage, chat_history: chatHistoryForBackend }),
      });

      // Handle HTTP errors explicitly so we can surface clear messages (e.g., rate limiting)
      if (!response.ok) {
        // Handle invalid challenge error - retry once with a fresh challenge
        if (response.status === 403) {
          try {
            const errorBody = await response.json();
            if (errorBody?.detail?.error === "invalid_challenge") {
              // Fetch a new challenge and retry once
              console.debug("Challenge invalid, fetching new challenge and retrying...");
              const newFingerprint = await ensureFreshFingerprint();
              
              if (newFingerprint) {
                headers["X-Fingerprint"] = newFingerprint;
                const retryResponse = await fetch(`${backendUrl}/api/v1/chat/stream`, {
                  method: "POST",
                  headers,
                  body: JSON.stringify({ query: trimmedMessage, chat_history: chatHistoryForBackend }),
                });
                
                if (retryResponse.ok) {
                  // Retry succeeded, replace response with retryResponse and continue
                  // We'll process it in the normal flow below
                  response = retryResponse;
                  // Skip the rest of error handling since retry succeeded
                } else {
                  // Retry also failed, show error
                  const retryErrorBody = await retryResponse.json().catch(() => ({}));
                  const retryMessage = retryErrorBody?.detail?.message || `HTTP error! status: ${retryResponse.status}`;
                  setStreamingMessage({
                    role: "ai",
                    content: retryMessage,
                    status: "error",
                    isStreamActive: false,
                  });
                  setIsLoading(false);
                  return;
                }
              } else {
                // Could not get new fingerprint, show error
                setStreamingMessage({
                  role: "ai",
                  content: errorBody?.detail?.message || "Invalid security challenge. Please refresh the page and try again.",
                  status: "error",
                  isStreamActive: false,
                });
                setIsLoading(false);
                return;
              }
            } else if (errorBody?.detail?.error === "too_many_challenges" || errorBody?.error === "too_many_challenges") {
              // Handle too_many_challenges error - store retry info in user message
              // Check both detail wrapper and top-level error data
              const detail = errorBody?.detail || errorBody;
              const retryAfterSeconds = detail?.retry_after_seconds ?? errorBody?.retry_after_seconds ?? 0;
              const banExpiresAt = detail?.ban_expires_at ?? errorBody?.ban_expires_at;
              const violationCount = detail?.violation_count ?? errorBody?.violation_count ?? 0;
              const errorMessage = detail?.message || errorBody?.message || "Too many requests. Please wait before trying again.";
              
              console.debug("Chat stream returned too_many_challenges error:", {
                messageId,
                retryAfterSeconds,
                banExpiresAt,
                violationCount,
                errorBody,
                detail,
              });
              
              // Parse banExpiresAt to ensure it's a number
              let parsedBanExpiresAt: number | undefined = undefined;
              if (banExpiresAt !== null && banExpiresAt !== undefined) {
                if (typeof banExpiresAt === 'number') {
                  parsedBanExpiresAt = banExpiresAt;
                } else {
                  const parsed = parseInt(String(banExpiresAt), 10);
                  if (!isNaN(parsed)) {
                    parsedBanExpiresAt = parsed;
                  }
                }
              }
              
              const retryInfoToStore = {
                retryAfterSeconds: Math.max(0, retryAfterSeconds || 0),
                banExpiresAt: parsedBanExpiresAt,
                violationCount: Math.max(0, violationCount || 0),
                errorType: "too_many_challenges",
                originalMessage: trimmedMessage,
              };
              
              console.debug("Storing retry info in message from chat stream error:", retryInfoToStore);
              
              // Update the user message with retry info
              setMessages((prevMessages) => {
                const updatedMessages = [...prevMessages];
                // Find message by ID to be more defensive
                const messageIndex = updatedMessages.findIndex(msg => msg.id === messageId);
                
                if (messageIndex >= 0) {
                  console.debug(`Found message at index ${messageIndex} for chat stream error, updating with retry info`);
                  updatedMessages[messageIndex] = {
                    ...updatedMessages[messageIndex],
                    retryInfo: retryInfoToStore,
                  };
                  console.debug("Updated message with retry info:", {
                    id: updatedMessages[messageIndex].id,
                    hasRetryInfo: !!updatedMessages[messageIndex].retryInfo,
                    retryInfo: updatedMessages[messageIndex].retryInfo,
                  });
                } else {
                  // Fallback to last message if ID not found
                  const lastMessageIndex = updatedMessages.length - 1;
                  if (lastMessageIndex >= 0) {
                    console.warn(`Message ${messageId} not found, updating last message at index ${lastMessageIndex} as fallback`);
                    updatedMessages[lastMessageIndex] = {
                      ...updatedMessages[lastMessageIndex],
                      retryInfo: retryInfoToStore,
                    };
                  } else {
                    console.error("No messages found to attach retry info to");
                  }
                }
                return updatedMessages;
              });
              
              // Show error message
              setStreamingMessage({
                role: "ai",
                content: errorMessage,
                status: "error",
                isStreamActive: false,
              });
              setIsLoading(false);
              return;
            } else {
              // Other 403 error, show message (errorBody already parsed above)
              setStreamingMessage({
                role: "ai",
                content: errorBody?.detail?.message || "Access forbidden. Please refresh the page and try again.",
                status: "error",
                isStreamActive: false,
              });
              setIsLoading(false);
              return;
            }
          } catch (parseError) {
            // If we can't parse the error, fall through to generic error handling
            console.debug("Could not parse error response:", parseError);
          }
        }
        
        // If response is still not ok after retry handling, continue with other error handling
        if (!response.ok && response.status === 429) {
          let errorBody: ErrorResponseData | null = null;
          let serverMessage: string | null = null;
          let errorType: string | null = null;
          
          try {
            errorBody = await response.json();
            if (errorBody && errorBody.detail) {
              // Handle both object and string detail formats
              if (typeof errorBody.detail === "object") {
                serverMessage = errorBody.detail.message || null;
                errorType = errorBody.detail.error || null;
              } else if (typeof errorBody.detail === "string") {
                serverMessage = errorBody.detail;
              }
            }
            // Also check top-level error fields
            if (!errorType && errorBody?.error) {
              errorType = errorBody.error;
            }
            if (!serverMessage && errorBody?.message) {
              serverMessage = errorBody.message;
            }
          } catch {
            // Ignore JSON parse errors and fall back to default message
          }

          // Handle cost_throttled errors similar to too_many_challenges
          if (errorType === "cost_throttled" || errorBody?.detail?.error === "cost_throttled" || errorBody?.error === "cost_throttled") {
            const detail = errorBody?.detail || errorBody;
            const errorMessage = serverMessage || detail?.message || errorBody?.message || "High usage detected. Please wait before trying again.";
            
            // Extract retry time from message
            const retryAfterSeconds = extractRetrySecondsFromMessage(errorMessage) || 30; // Default to 30 seconds if parsing fails
            
            console.debug("Chat stream returned cost_throttled error:", {
              messageId,
              retryAfterSeconds,
              errorMessage,
              errorBody,
              detail,
            });
            
            const retryInfoToStore = {
              retryAfterSeconds: Math.max(0, retryAfterSeconds),
              banExpiresAt: undefined, // cost_throttled doesn't use ban_expires_at
              violationCount: 0, // cost_throttled doesn't track violation count
              errorType: "cost_throttled",
              originalMessage: trimmedMessage,
            };
            
            console.debug("Storing retry info in message from cost_throttled error:", retryInfoToStore);
            
            // Update the user message with retry info
            setMessages((prevMessages) => {
              const updatedMessages = [...prevMessages];
              // Find message by ID to be more defensive
              const messageIndex = updatedMessages.findIndex(msg => msg.id === messageId);
              
              if (messageIndex >= 0) {
                console.debug(`Found message at index ${messageIndex} for cost_throttled error, updating with retry info`);
                updatedMessages[messageIndex] = {
                  ...updatedMessages[messageIndex],
                  retryInfo: retryInfoToStore,
                };
                console.debug("Updated message with retry info:", {
                  id: updatedMessages[messageIndex].id,
                  hasRetryInfo: !!updatedMessages[messageIndex].retryInfo,
                  retryInfo: updatedMessages[messageIndex].retryInfo,
                });
              } else {
                // Fallback to last message if ID not found
                const lastMessageIndex = updatedMessages.length - 1;
                if (lastMessageIndex >= 0) {
                  console.warn(`Message ${messageId} not found, updating last message at index ${lastMessageIndex} as fallback`);
                  updatedMessages[lastMessageIndex] = {
                    ...updatedMessages[lastMessageIndex],
                    retryInfo: retryInfoToStore,
                  };
                } else {
                  console.error("No messages found to attach retry info to");
                }
              }
              return updatedMessages;
            });
            
            // Show error message
            setStreamingMessage({
              role: "ai",
              content: errorMessage,
              status: "error",
              isStreamActive: false,
            });
            setIsLoading(false);
            return;
          }

          // Handle generic 429 errors (not cost_throttled)
          let retryAfterSeconds: number | null = null;
          const retryAfterHeader = response.headers.get("Retry-After");
          if (retryAfterHeader) {
            const parsed = parseInt(retryAfterHeader, 10);
            if (!Number.isNaN(parsed)) {
              retryAfterSeconds = parsed;
            }
          }

          const humanReadableRetry =
            retryAfterSeconds && retryAfterSeconds >= 60
              ? `${Math.round(retryAfterSeconds / 60)} minute${retryAfterSeconds >= 120 ? "s" : ""}`
              : retryAfterSeconds
              ? `${retryAfterSeconds} seconds`
              : null;

          const content =
            serverMessage ||
            (humanReadableRetry
              ? `You're sending messages too quickly. Please wait about ${humanReadableRetry} and try again.`
              : "You're sending messages too quickly. Please wait a bit and try again.");

          setStreamingMessage({
            role: "ai",
            content,
            status: "error",
            isStreamActive: false,
          });
          setIsLoading(false);
          return;
        }

        throw new Error(`HTTP error! status: ${response.status}`);
      }

      reader = response.body?.getReader() || null;
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error("Response body is not readable");
      }
      // Important: TypeScript won't narrow a captured mutable variable (`reader`) inside closures.
      // Bind a non-null constant and use it throughout the streaming code.
      const streamReader = reader;
      streamReaderRef.current = streamReader;

      let accumulatedContent = "";
      let buffer = "";
      let shouldBreak = false;

      // Helper function to check if tab is visible
      const isTabVisible = () => {
        return !document.hidden;
      };

      // Type for SSE data objects
      type SSEData = 
        | { status: 'thinking' }
        | { status: 'streaming'; chunk: string }
        | { status: 'follow_ups'; questions?: string[] }
        | { status: 'complete' }
        | { status: 'error'; error?: string }
        | { status: 'usage_status'; usage_status?: { status: string; warning_level: string | null } };

      // Helper function to process a single SSE data object
      const processData = async (data: SSEData) => {
        if (streamId !== activeStreamIdRef.current) {
          // Conversation was cleared (or a newer stream started) — stop processing.
          shouldBreak = true;
          return;
        }
        if (data.status === 'usage_status') {
          // Handle usage status from stream
          if (data.usage_status && data.usage_status.warning_level) {
            setUsageWarning({
              status: data.usage_status.status,
              warning_level: data.usage_status.warning_level as "error" | "warning" | "info",
            });
          } else {
            setUsageWarning(null);
          }
        } else if (data.status === 'thinking') {
          setStreamingMessage(prev => prev ? { ...prev, status: 'thinking' } : null);
        } else if (data.status === 'streaming') {
          // When tab is hidden, process chunks immediately without delay to avoid throttling
          const tabVisible = isTabVisible();
          
          if (tabVisible) {
            // Accumulate characters and display word by word (only when tab is visible)
            let wordBuffer = "";
            for (const char of data.chunk) {
              wordBuffer += char;
              accumulatedContent += char;

              // Check if we've completed a word (space, punctuation, or end of chunk)
              const isWordBoundary = char === ' ' || char === '\n' || char === '.' || char === '!' || char === '?' || char === ',' || char === ';' || char === ':';

              if (isWordBoundary || wordBuffer.length > 20) { // Also break long words
                setStreamingMessage(prev => prev ? {
                  ...prev,
                  content: accumulatedContent,
                  status: 'streaming',
                  isStreamActive: true
                } : null);
                // Delay between words for natural typing rhythm (only when visible)
                await new Promise(resolve => setTimeout(resolve, 25));
                wordBuffer = "";
              }
            }

            // Display any remaining characters in the buffer
            if (wordBuffer.length > 0) {
              setStreamingMessage(prev => prev ? {
                ...prev,
                content: accumulatedContent,
                status: 'streaming',
                isStreamActive: true
              } : null);
            }
          } else {
            // Tab is hidden - process entire chunk immediately without delay
            accumulatedContent += data.chunk;
            setStreamingMessage(prev => prev ? {
              ...prev,
              content: accumulatedContent,
              status: 'streaming',
              isStreamActive: true
            } : null);
          }
        } else if (data.status === 'follow_ups') {
          setStreamingMessage(prev => prev ? {
            ...prev,
            followUpQuestions: data.questions || []
          } : null);
        } else if (data.status === 'complete') {
          setStreamingMessage(prev => prev ? {
            ...prev,
            content: accumulatedContent,
            status: 'complete',
            isStreamActive: false
          } : null);
          shouldBreak = true;
        } else if (data.status === 'error') {
          setStreamingMessage(prev => prev ? {
            ...prev,
            content: data.error || "An error occurred",
            status: 'error',
            isStreamActive: false
          } : null);
          shouldBreak = true;
        }
      };

      const processStream = async () => {
        try {
          while (true) {
            if (streamId !== activeStreamIdRef.current) {
              shouldBreak = true;
              break;
            }
            const { done, value } = await streamReader.read();
            if (done) {
              // Process any remaining buffer content
              if (buffer.trim()) {
                const lines = buffer.split('\n');
                for (const line of lines) {
                  if (line.startsWith('data: ')) {
                    try {
                      const jsonStr = line.slice(6).trim();
                      if (!jsonStr) continue;
                      const data = JSON.parse(jsonStr);
                      await processData(data);
                      if (shouldBreak) break;
                    } catch (parseError) {
                      console.error('Error parsing final SSE data:', parseError);
                    }
                  }
                }
              }
              break;
            }

            // Decode chunk and append to buffer
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            // Process complete lines (lines ending with \n)
            const lines = buffer.split('\n');
            // Keep the last incomplete line in the buffer
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const jsonStr = line.slice(6).trim();
                  // Skip empty lines
                  if (!jsonStr) continue;
                  
                  const data = JSON.parse(jsonStr);
                  await processData(data);
                  if (shouldBreak) break;
                } catch (parseError) {
                  // Log parse error without exposing potentially sensitive data
                  console.error('Error parsing SSE data:', parseError);
                  // Continue processing other lines instead of breaking
                }
              }
            }
            
            if (shouldBreak) break;
          }
        } catch (error) {
          // If the conversation was cleared (or a newer stream started), swallow any errors from canceling/abandoning.
          if (streamId === activeStreamIdRef.current) {
            console.error('Stream processing error:', error);
            setStreamingMessage(prev => prev ? {
              ...prev,
              content: "Sorry, something went wrong. Please try again.",
              status: 'error',
              isStreamActive: false
            } : null);
          }
        }
      };

      await processStream();

    } catch (error) {
      console.error("Error sending message:", error);
      if (streamId === activeStreamIdRef.current) {
        setStreamingMessage({
          role: "ai",
          content: "Sorry, something went wrong. Please try again.",
          status: 'error',
          isStreamActive: false
        });
      }
    } finally {
      // Only clear the reader ref if it still points at this stream's reader.
      if (reader && streamReaderRef.current && streamReaderRef.current === reader) {
        streamReaderRef.current = null;
      }
      // Avoid old streams flipping loading state after a newer stream starts (or after clearing).
      if (streamId === activeStreamIdRef.current) {
        setIsLoading(false);
      }
    }
  };

  // Effect to clear pinned message ID when streaming completes
  useEffect(() => {
    if (streamingMessage && (streamingMessage.status === 'complete' || streamingMessage.status === 'error')) {
      // Keep the message pinned even after streaming completes
      // The spacer logic will handle maintaining empty space for short messages
      // and transitioning to native scrolling for long messages
    }
  }, [streamingMessage]);

  // Effect to move completed streaming message to messages array
  useEffect(() => {
    if (streamingMessage && streamingMessage.status === 'complete') {
      setMessages(prev => [...prev, {
        role: streamingMessage.role,
        content: streamingMessage.content,
        followUpQuestions: streamingMessage.followUpQuestions
      }]);
      setStreamingMessage(null);
    } else if (streamingMessage && streamingMessage.status === 'error') {
      setMessages(prev => [...prev, {
        role: streamingMessage.role,
        content: streamingMessage.content,
        followUpQuestions: streamingMessage.followUpQuestions
      }]);
      setStreamingMessage(null);
    }
  }, [streamingMessage]);

  return (
    <div className="flex flex-col h-screen max-h-screen relative z-10">
      
      {/* Usage Warning Banner */}
      {usageWarning && usageWarning.warning_level && (
        <div
          className={`px-4 py-2 text-sm text-center ${
            usageWarning.warning_level === "error"
              ? "bg-red-100 text-red-800 border-b border-red-200"
              : usageWarning.warning_level === "warning"
              ? "bg-yellow-100 text-yellow-800 border-b border-yellow-200"
              : "bg-blue-100 text-blue-800 border-b border-blue-200"
          }`}
        >
          {usageWarning.warning_level === "error" ? (
            <span>
              ⚠️ Service temporarily unavailable due to high usage. Please try again later.
            </span>
          ) : usageWarning.warning_level === "warning" ? (
            <span>
              ⚠️ High usage detected. Service may be limited soon.
            </span>
          ) : (
            <span>
              ℹ️ Usage approaching limits. Service may be limited soon.
            </span>
          )}
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-hidden relative z-10">
        {messages.length === 0 && !streamingMessage && !isLoading ? (
          <div className="flex items-center justify-center h-full relative z-10">
            <SuggestedQuestions onQuestionClick={handleSendMessage} />
          </div>
        ) : (
          <ChatWindow 
            ref={chatWindowRef} 
            shouldScrollToBottom={false}
            onScrollChange={setScrollPosition}
            pinnedMessageId={pinnedMessageId}
          >
            {messages.map((msg, index) => (
              <Message
                key={msg.id || index}
                messageId={msg.id}
                role={msg.role === "human" ? "user" : "assistant"}
                content={msg.content}
                followUpQuestions={msg.followUpQuestions}
                retryInfo={msg.retryInfo}
                onFollowUpClick={handleSendMessage}
                onRetry={msg.retryInfo?.originalMessage ? () => handleRetryMessage(msg.id!, msg.retryInfo!.originalMessage!) : undefined}
              />
            ))}
            {streamingMessage && (
              <StreamingMessage
                content={streamingMessage.content}
                status={streamingMessage.status || "thinking"}
                isStreamActive={streamingMessage.isStreamActive || false}
              />
            )}
            {!streamingMessage && isLoading && <MessageLoader />}
          </ChatWindow>
        )}
        <InputBox
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          showConversationActions={messages.length > 0 || !!streamingMessage || isLoading}
          onClearConversation={clearConversation}
        />
      </div>
      
    </div>
  );
}
