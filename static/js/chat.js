const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const chatHistory = document.querySelector("#chat-history");
const emptyState = document.querySelector("#empty-state");
const sendButton = document.querySelector("#send-button");
const newChatButton = document.querySelector("#new-chat-button");
const loadingIndicator = document.querySelector("#loading-indicator");
const errorMessage = document.querySelector("#error-message");

const HISTORY_STORAGE_KEY = "nova-ai-chat-history";
const MAX_HISTORY_MESSAGES = 20;
const MAX_USER_MESSAGE_CHARS = 4000;
const MAX_ASSISTANT_MESSAGE_CHARS = 12000;

function appendMessage(text, role) {
    const messageBubble = document.createElement("p");
    messageBubble.className = `chat-message chat-message--${role}`;
    messageBubble.textContent = text;
    chatHistory.append(messageBubble);
    return messageBubble;
}

function scrollToLatestMessage() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.hidden = false;
}

function clearStoredHistory() {
    try {
        sessionStorage.removeItem(HISTORY_STORAGE_KEY);
        return true;
    } catch {
        return false;
    }
}

function isValidStoredMessage(message, index) {
    if (!message || typeof message !== "object" || Array.isArray(message)) {
        return false;
    }

    const expectedRole = index % 2 === 0 ? "user" : "assistant";
    const maxChars =
        expectedRole === "user" ? MAX_USER_MESSAGE_CHARS : MAX_ASSISTANT_MESSAGE_CHARS;

    return (
        message.role === expectedRole &&
        typeof message.content === "string" &&
        message.content.trim().length > 0 &&
        message.content.length <= maxChars
    );
}

function loadConversationHistory() {
    let savedHistory;
    try {
        savedHistory = sessionStorage.getItem(HISTORY_STORAGE_KEY);
    } catch {
        showError("This browser tab cannot access saved conversation storage.");
        return [];
    }

    if (!savedHistory) {
        return [];
    }

    let messages;
    try {
        messages = JSON.parse(savedHistory);
    } catch {
        const cleared = clearStoredHistory();
        showError(
            cleared
                ? "Saved conversation data was invalid and has been cleared."
                : "Saved conversation data was invalid, but this browser could not clear it.",
        );
        return [];
    }

    const validHistory =
        Array.isArray(messages) &&
        messages.length <= MAX_HISTORY_MESSAGES &&
        messages.length % 2 === 0 &&
        messages.every(isValidStoredMessage);

    if (!validHistory) {
        const cleared = clearStoredHistory();
        showError(
            cleared
                ? "Saved conversation data was invalid and has been cleared."
                : "Saved conversation data was invalid, but this browser could not clear it.",
        );
        return [];
    }

    return messages;
}

let conversationHistory = loadConversationHistory();

if (conversationHistory.length > 0) {
    emptyState.remove();
    for (const message of conversationHistory) {
        appendMessage(message.content, message.role);
    }
    scrollToLatestMessage();
}

sendButton.disabled = false;

messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!sendButton.disabled) {
            chatForm.requestSubmit();
        }
    }
});

newChatButton.addEventListener("click", () => {
    const cleared = clearStoredHistory();
    conversationHistory = [];
    chatHistory.replaceChildren(emptyState);
    if (cleared) {
        errorMessage.hidden = true;
        errorMessage.textContent = "";
    } else {
        showError(
            "The chat was cleared for now, but this browser could not remove saved history. Refreshing may restore it.",
        );
    }
    messageInput.value = "";
    messageInput.focus();
});

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const messageText = messageInput.value.trim();
    if (!messageText) {
        messageInput.focus();
        return;
    }

    const previousMessages = conversationHistory.slice(-(MAX_HISTORY_MESSAGES - 2));
    const messagesForRequest = [
        ...previousMessages,
        { role: "user", content: messageText },
    ];

    if (emptyState.isConnected) {
        emptyState.remove();
    }
    const userBubble = appendMessage(messageText, "user");
    scrollToLatestMessage();

    messageInput.value = "";
    errorMessage.hidden = true;
    errorMessage.textContent = "";
    loadingIndicator.hidden = false;
    sendButton.disabled = true;
    newChatButton.disabled = true;
    messageInput.disabled = true;

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ messages: messagesForRequest }),
        });
        const result = await response.json().catch(() => null);

        if (!response.ok) {
            const serverMessage =
                result && typeof result.error === "string"
                    ? result.error
                    : `The server returned HTTP ${response.status}.`;
            throw new Error(serverMessage);
        }

        if (!result || typeof result.response !== "string" || !result.response.trim()) {
            throw new Error("The server returned an invalid response.");
        }

        appendMessage(result.response, "assistant");
        conversationHistory = [
            ...messagesForRequest,
            { role: "assistant", content: result.response },
        ].slice(-MAX_HISTORY_MESSAGES);
        try {
            sessionStorage.setItem(
                HISTORY_STORAGE_KEY,
                JSON.stringify(conversationHistory),
            );
        } catch {
            showError("Reply received, but this tab could not save the conversation.");
        }
    } catch (error) {
        userBubble.remove();
        if (conversationHistory.length === 0) {
            chatHistory.append(emptyState);
        }
        messageInput.value = messageText;
        showError(
            error instanceof TypeError
                ? "Could not connect to the chat service. Check that Flask is running."
                : error instanceof Error
                  ? error.message
                  : "Something went wrong. Please try again.",
        );
    } finally {
        loadingIndicator.hidden = true;
        sendButton.disabled = false;
        newChatButton.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
        scrollToLatestMessage();
    }
});
