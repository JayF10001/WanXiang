import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Home, MoreVertical, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Trash2 } from 'lucide-react';
import type { ChatSession } from '../types/assistant';

export const Sidebar = ({
  onHome,
  onNewChat,
  isCollapsed,
  setIsCollapsed,
  showHomeButton = true,
  onSelectHistory,
  activeHistory,
  sessions = [],
  onRenameSession,
  onDeleteSession,
}: {
  onHome: () => void;
  onNewChat: () => void;
  isCollapsed: boolean;
  setIsCollapsed: (value: boolean) => void;
  showHomeButton?: boolean;
  onSelectHistory?: (sessionId: string) => void;
  activeHistory?: string | null;
  sessions?: ChatSession[];
  onRenameSession?: (sessionId: string, currentTitle: string) => void;
  onDeleteSession?: (sessionId: string) => void;
}) => {
  const MENU_WIDTH = 144;
  const MENU_HEIGHT = 104;
  const VIEWPORT_PADDING = 12;
  const [menuState, setMenuState] = useState<{
    sessionId: string;
    placement: 'top' | 'bottom';
    top: number;
    left: number;
  } | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const buildMenuPosition = (trigger: HTMLButtonElement) => {
    const rect = trigger.getBoundingClientRect();
    const shouldOpenUpward =
      rect.top >= window.innerHeight * 0.65 ||
      rect.bottom + MENU_HEIGHT + VIEWPORT_PADDING > window.innerHeight;
    const placement = shouldOpenUpward ? 'bottom' : 'top';
    const left = Math.min(
      window.innerWidth - MENU_WIDTH - VIEWPORT_PADDING,
      Math.max(VIEWPORT_PADDING, rect.right - MENU_WIDTH),
    );
    const top = placement === 'bottom' ? rect.top - 6 : rect.bottom + 6;
    return { placement, top, left };
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const activeTrigger = menuState ? triggerRefs.current[menuState.sessionId] : null;
      if (activeTrigger && activeTrigger.contains(event.target as Node)) {
        return;
      }
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuState(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuState]);

  useEffect(() => {
    if (!menuState) {
      return;
    }

    const handleViewportChange = () => {
      const activeTrigger = triggerRefs.current[menuState.sessionId];
      if (!activeTrigger) {
        setMenuState(null);
        return;
      }
      setMenuState((previous) => (
        previous
          ? { ...previous, ...buildMenuPosition(activeTrigger) }
          : previous
      ));
    };

    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [menuState]);

  if (isCollapsed) {
    return (
      <div className="w-16 bg-white/70 backdrop-blur-xl border-r border-white/50 flex flex-col flex-shrink-0 z-10 shadow-[4px_0_24px_rgba(0,0,0,0.02)] transition-all duration-300">
        <div className="p-4 border-b border-gray-100 flex justify-center">
          <button onClick={() => setIsCollapsed(false)} className="text-gray-500 hover:bg-gray-100 p-2 rounded-lg transition-colors">
            <PanelLeftOpen size={20} />
          </button>
        </div>
        <div className="p-4 flex flex-col items-center gap-4 flex-1 overflow-y-auto scrollbar-hide">
          {showHomeButton && (
            <button onClick={onHome} className="text-blue-600 hover:bg-blue-50 p-2 rounded-lg transition-colors" title="主页">
              <Home size={20} />
            </button>
          )}
          <button onClick={onNewChat} className="text-gray-500 hover:bg-gray-100 p-2 rounded-lg transition-colors" title="新建">
            <Plus size={20} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 bg-white/70 backdrop-blur-xl border-r border-white/50 flex flex-col flex-shrink-0 z-10 shadow-[4px_0_24px_rgba(0,0,0,0.02)] transition-all duration-300">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        {showHomeButton ? (
          <button onClick={onHome} className="flex items-center text-blue-600 font-medium hover:bg-blue-50 px-3 py-2 rounded-lg transition-colors flex-1 mr-2">
            <Home size={18} className="mr-2" /> 回主页
          </button>
        ) : (
          <div className="flex-1"></div>
        )}
        <button
          onClick={() => setIsCollapsed(true)}
          className="flex items-center gap-1.5 text-gray-500 hover:bg-gray-100 px-2.5 py-2 rounded-lg transition-colors flex-shrink-0"
          title="收起侧栏"
        >
          <PanelLeftClose size={18} />
          <span className="text-sm">收起</span>
        </button>
      </div>
      <div className="p-4 flex-1 overflow-y-auto scrollbar-hide">
        <div className="flex items-center justify-between text-gray-500 text-sm mb-4">
          <span>列表</span>
          <button onClick={onNewChat} className="hover:bg-gray-100 p-1 rounded"><Plus size={16} /></button>
        </div>
        <div className="space-y-1">
          {sessions.map((item) => {
            const isActive = activeHistory === item.id;
            const isMenuOpen = menuState?.sessionId === item.id;
            return (
              <div
                key={item.id}
                className={`w-full px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors ${
                  isActive 
                    ? 'bg-blue-50 text-blue-600' 
                    : 'text-gray-600 hover:bg-gray-200 hover:text-gray-900'
                }`}
              >
                <button
                  onClick={() => onSelectHistory?.(item.id)}
                  className="-my-2 -ml-3 flex-1 min-w-0 rounded-lg px-3 py-2 text-left"
                >
                  <span className="truncate block">{item.title}</span>
                </button>
                <div className="relative flex-shrink-0">
                  <button
                    ref={(node) => {
                      triggerRefs.current[item.id] = node;
                    }}
                    onClick={(event) => {
                      const nextPosition = buildMenuPosition(event.currentTarget);
                      setMenuState((previous) => (
                        previous?.sessionId === item.id ? null : { sessionId: item.id, ...nextPosition }
                      ));
                    }}
                    className={`-my-1 rounded-md p-2 transition-colors ${isActive ? 'text-blue-500 hover:bg-blue-100' : 'text-gray-400 hover:bg-gray-300 hover:text-gray-700'}`}
                    title="会话操作"
                  >
                    <MoreVertical size={16} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {menuState && typeof document !== 'undefined' && createPortal(
        <div
          ref={menuRef}
          className="fixed z-[99999] w-36 rounded-xl border border-gray-100 bg-white shadow-xl py-1"
          style={{
            left: menuState.left,
            top: menuState.top,
            transform: menuState.placement === 'bottom' ? 'translateY(-100%)' : 'none',
          }}
        >
          <button
            onClick={() => {
              const target = sessions.find((session) => session.id === menuState.sessionId);
              setMenuState(null);
              if (target) {
                onRenameSession?.(target.id, target.title);
              }
            }}
            className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
          >
            <Pencil size={14} />
            重命名
          </button>
          <button
            onClick={() => {
              const target = sessions.find((session) => session.id === menuState.sessionId);
              setMenuState(null);
              if (target) {
                onDeleteSession?.(target.id);
              }
            }}
            className="w-full px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
          >
            <Trash2 size={14} />
            删除
          </button>
        </div>,
        document.body
      )}
    </div>
  );
};
