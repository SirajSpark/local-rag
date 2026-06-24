import { useState } from "react";
import { PanelLeftOpen, PanelLeftClose } from "lucide-react";
import { UploadForm } from "./components/documents/UploadForm";
import { DocumentList } from "./components/documents/DocumentList";
import { ChatWindow } from "./components/chat/ChatWindow";
import { useChat } from "./hooks/useChat";
import { cn } from "./lib/utils";

export default function App() {
  const { messages, isLoading, sendMessage, clearMessages } = useChat();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="flex h-screen flex-col bg-zinc-950">
      <header className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-3">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          {sidebarOpen ? (
            <PanelLeftClose className="h-4 w-4" />
          ) : (
            <PanelLeftOpen className="h-4 w-4" />
          )}
        </button>
        <h1 className="text-sm font-semibold text-zinc-100">Local RAG</h1>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside
          className={cn(
            "flex flex-col border-r border-zinc-800 bg-zinc-900 transition-all duration-300 ease-in-out overflow-hidden",
            sidebarOpen ? "w-80" : "w-0",
          )}
        >
          <div className="w-80 border-b border-zinc-800 p-4">
            <UploadForm />
          </div>
          <div className="w-80 flex-1 overflow-y-auto p-4">
            <DocumentList />
          </div>
        </aside>

        <main className="flex flex-1 flex-col">
          <ChatWindow
            messages={messages}
            isLoading={isLoading}
            onSend={sendMessage}
            onClear={clearMessages}
          />
        </main>
      </div>
    </div>
  );
}
