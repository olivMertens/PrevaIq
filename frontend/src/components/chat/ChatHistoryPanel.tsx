'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { 
  MessageSquare, 
  Plus, 
  Trash2, 
  Clock, 
  ChevronLeft, 
  ChevronRight,
  Loader2,
  AlertCircle,
  RefreshCw,
  Globe,
  FileText
} from 'lucide-react';
import { APIError, deleteConversation, listConversations, type ConversationSummary } from '@/lib/api';

export type { ConversationSummary } from '@/lib/api';

declare global {
  interface Window {
    __refreshChatHistory?: () => Promise<void>;
  }
}

type HistoryTab = 'app' | 'all';
type HistoryState = {
  scope: string;
  conversations: ConversationSummary[];
  isLoading: boolean;
  error: string | null;
};

interface ChatHistoryPanelProps {
  applicationId: string;
  currentConversationId: string | null;
  onSelectConversation: (id: string | null, applicationId?: string, persona?: string) => void;
  onNewConversation: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export default function ChatHistoryPanel({
  applicationId,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  isCollapsed,
  onToggleCollapse,
}: ChatHistoryPanelProps) {
  const [activeTab, setActiveTab] = useState<HistoryTab>('app');
  const [history, setHistory] = useState<HistoryState>({
    scope: '', conversations: [], isLoading: true, error: null,
  });
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const selection = useRef({applicationId, currentConversationId});
  const t = useTranslations('chatHistory');
  const locale = useLocale();
  const scope = activeTab === 'app' ? `app:${applicationId}` : 'all';
  const current = activeTab === 'app' && !applicationId
    ? {scope, conversations: [], isLoading: false, error: null}
    : history.scope === scope ? history : {scope, conversations: [], isLoading: true, error: null};
  const {conversations, isLoading, error} = current;

  useEffect(() => {
    selection.current = {applicationId, currentConversationId};
  }, [applicationId, currentConversationId]);

  const reportFailure = useCallback((failure: unknown, operation: 'load' | 'delete') => {
    const status = failure instanceof APIError ? failure.status : null;
    const code = failure instanceof APIError ? failure.code : undefined;
    const detail = code === 'invalid_conversation_history'
      ? t('invalidResponse')
      : status ? t('httpStatus', {status}) : t('connectionError');
    const message = `${t(operation === 'load' ? 'loadError' : 'deleteError')} · ${detail}`;
    console.warn('chat.history.request_failed', {operation, status, code});
    return message;
  }, [t]);

  const loadHistory = useCallback((controller: AbortController) => (
    listConversations(activeTab === 'app' ? applicationId : undefined, controller.signal)
    .then(loaded => {
      if (controller.signal.aborted) return;
      setHistory({scope, conversations: loaded, isLoading: false, error: null});
    })
    .catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      const message = reportFailure(failure, 'load');
      setHistory(previous => ({
        scope,
        conversations: previous.scope === scope ? previous.conversations : [],
        isLoading: false,
        error: message,
      }));
    })
  ), [activeTab, applicationId, scope, reportFailure]);

  const refreshConversations = useCallback(async () => {
    request.current?.abort();
    if (activeTab === 'app' && !applicationId) return;
    const controller = new AbortController();
    request.current = controller;
    setHistory(previous => ({
      scope,
      conversations: previous.scope === scope ? previous.conversations : [],
      isLoading: true,
      error: null,
    }));
    await loadHistory(controller);
  }, [scope, activeTab, applicationId, loadHistory]);

  useEffect(() => {
    if (activeTab === 'app' && !applicationId) return;
    const controller = new AbortController();
    request.current = controller;
    void loadHistory(controller);
    return () => request.current?.abort();
  }, [scope, activeTab, applicationId, loadHistory]);

  useEffect(() => {
    window.__refreshChatHistory = refreshConversations;
    return () => {
      if (window.__refreshChatHistory === refreshConversations) delete window.__refreshChatHistory;
    };
  }, [refreshConversations]);

  const handleDelete = async (e: React.MouseEvent, conversationId: string, convAppId?: string) => {
    e.stopPropagation();
    if (deletingId) return;
    
    const targetAppId = convAppId || applicationId;
    
    setDeletingId(conversationId);
    try {
      await deleteConversation(targetAppId, conversationId);
      setHistory(previous => ({
        ...previous,
        conversations: previous.conversations.filter(c =>
          c.id !== conversationId || c.application_id !== targetAppId),
      }));
      if (selection.current.applicationId === targetAppId
        && selection.current.currentConversationId === conversationId) {
        onSelectConversation(null);
      }
    } catch (failure) {
      const message = reportFailure(failure, 'delete');
      setHistory(previous => previous.scope === scope ? {...previous, error: message} : previous);
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return t('justNow');
    if (diffMins < 60) return t('minutesAgo', { count: diffMins });
    if (diffHours < 24) return t('hoursAgo', { count: diffHours });
    if (diffDays < 7) return t('daysAgo', { count: diffDays });
    return date.toLocaleDateString(locale);
  };

  // Collapsed state
  if (isCollapsed) {
    return (
      <aside aria-label={t('history')} className="w-12 bg-slate-100 border-r border-slate-200 flex flex-col items-center py-3 gap-2">
        <button
          onClick={onToggleCollapse}
          className="p-2 hover:bg-slate-200 rounded-lg transition-colors"
          title={t('expandHistory')}
        >
          <ChevronRight className="w-4 h-4 text-slate-600" />
        </button>
        <button
          onClick={onNewConversation}
          className="p-2 hover:bg-indigo-100 rounded-lg transition-colors"
          title={t('newConversation')}
        >
          <Plus className="w-4 h-4 text-indigo-600" />
        </button>
        <div className="flex-1" />
        {error && <button type="button" onClick={() => void refreshConversations()}
          title={`${error} · ${t('retry')}`} aria-label={t('retry')}
          className="rounded-lg p-2 text-amber-700 hover:bg-amber-100">
          <AlertCircle className="h-4 w-4" aria-hidden />
        </button>}
        <div className="text-xs text-slate-400 transform -rotate-90 whitespace-nowrap">
          {error ? t('unavailable') : t('chatCount', { count: conversations.length })}
        </div>
      </aside>
    );
  }

  return (
    <aside aria-label={t('history')} className="w-56 bg-slate-50 border-r border-slate-200 flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium text-slate-700">{t('history')}</span>
        </div>
        <button
          onClick={onToggleCollapse}
          className="p-1 hover:bg-slate-200 rounded transition-colors"
          title={t('collapse')}
        >
          <ChevronLeft className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Tab Switcher */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('app')}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium transition-colors ${
            activeTab === 'app'
              ? 'text-indigo-600 border-b-2 border-indigo-600 bg-white'
              : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
          }`}
          title={t('currentAppConversations')}
        >
          <FileText className="w-4 h-4" />
          <span>{t('current')}</span>
        </button>
        <button
          onClick={() => setActiveTab('all')}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium transition-colors ${
            activeTab === 'all'
              ? 'text-indigo-600 border-b-2 border-indigo-600 bg-white'
              : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
          }`}
          title={t('allAppsConversations')}
        >
          <Globe className="w-4 h-4" />
          <span>{t('allApps')}</span>
        </button>
      </div>

      {/* New Conversation Button */}
      <div className="p-2">
        <button
          onClick={onNewConversation}
          className="w-full flex items-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          {t('newChat')}
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <div role="alert" className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <AlertCircle className="w-5 h-5 text-slate-400 mb-2" />
            <p className="text-xs text-slate-500">{error}</p>
            <button type="button" onClick={() => void refreshConversations()} aria-label={t('retry')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-100">
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />{t('retry')}
            </button>
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <MessageSquare className="w-8 h-8 text-slate-300 mb-2" />
            <p className="text-xs text-slate-500">
              {activeTab === 'app' ? t('noConversationsYet') : t('noConversationsFound')}
            </p>
            <p className="text-xs text-slate-400">
              {activeTab === 'app' ? t('startNewChat') : t('startChattingAnyApp')}
            </p>
          </div>
        ) : (
          conversations.map((conv) => {
            const isFromDifferentApp = activeTab === 'all' && conv.application_id !== applicationId;
            return (
              <div
                key={`${conv.application_id}-${conv.id}`}
                className={`w-full text-left p-2 rounded-lg transition-colors group ${
                  currentConversationId === conv.id && conv.application_id === applicationId
                    ? 'bg-indigo-100 border border-indigo-200'
                    : isFromDifferentApp
                      ? 'hover:bg-amber-50 border border-transparent'
                      : 'hover:bg-slate-100 border border-transparent'
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <button type="button" className="min-w-0 flex-1 text-left"
                    onClick={() => onSelectConversation(conv.id, conv.application_id, conv.persona ?? undefined)}>
                    {/* Show app ID badge for global view */}
                    {activeTab === 'all' && (
                      <div className={`inline-block text-[10px] font-mono px-1.5 py-0.5 rounded mb-1 ${
                        isFromDifferentApp 
                          ? 'bg-amber-100 text-amber-700' 
                          : 'bg-indigo-100 text-indigo-700'
                      }`}>
                        {conv.application_id}
                      </div>
                    )}
                    <p className={`text-xs font-medium truncate ${
                      currentConversationId === conv.id && conv.application_id === applicationId 
                        ? 'text-indigo-800' 
                        : 'text-slate-700'
                    }`}>
                      {conv.title}
                    </p>
                    {conv.preview && (
                      <p className="text-xs text-slate-500 truncate mt-0.5">
                        {conv.preview}
                      </p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-400">
                        {formatDate(conv.updated_at)}
                      </span>
                      <span className="text-xs text-slate-400">
                        {conv.message_count} {t('msgs')}
                      </span>
                    </div>
                  </button>
                  <button
                    type="button" disabled={Boolean(deletingId)}
                    onClick={(e) => handleDelete(e, conv.id, conv.application_id)}
                    className={`p-1 rounded opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity ${
                      deletingId === conv.id ? 'opacity-100' : ''
                    } hover:bg-rose-100`}
                    title={t('delete')}
                  >
                    {deletingId === conv.id ? (
                      <Loader2 className="w-3 h-3 text-rose-500 animate-spin" />
                    ) : (
                      <Trash2 className="w-3 h-3 text-rose-500" />
                    )}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
