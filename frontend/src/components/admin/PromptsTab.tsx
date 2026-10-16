'use client';

import { useTranslations } from 'next-intl';
import type { PromptsData } from './types';

interface PromptsTabProps {
  promptsData: PromptsData | null;
  selectedSection: string;
  setSelectedSection: (s: string) => void;
  selectedSubsection: string;
  setSelectedSubsection: (s: string) => void;
  promptText: string;
  setPromptText: (s: string) => void;
  promptsLoading: boolean;
  promptsSaving: boolean;
  promptsError: string | null;
  promptsSuccess: string | null;
  showNewPromptForm: boolean;
  setShowNewPromptForm: (v: boolean) => void;
  newSection: string;
  setNewSection: (s: string) => void;
  newSubsection: string;
  setNewSubsection: (s: string) => void;
  newPromptText: string;
  setNewPromptText: (s: string) => void;
  onSavePrompt: () => void;
  onDeletePrompt: () => void;
  onCreatePrompt: () => void;
}

export default function PromptsTab({
  promptsData,
  selectedSection,
  setSelectedSection,
  selectedSubsection,
  setSelectedSubsection,
  promptText,
  setPromptText,
  promptsLoading,
  promptsSaving,
  promptsError,
  promptsSuccess,
  showNewPromptForm,
  setShowNewPromptForm,
  newSection,
  setNewSection,
  newSubsection,
  setNewSubsection,
  newPromptText,
  setNewPromptText,
  onSavePrompt,
  onDeletePrompt,
  onCreatePrompt,
}: PromptsTabProps) {
  const t = useTranslations('adminPanel');
  const tp = useTranslations('adminLabels');

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      {/* Skill Selector */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-xl font-semibold mb-4 text-slate-900">{t('agentSkills')}</h2>

        {promptsLoading ? (
          <div className="text-center py-8 text-slate-500">{t('loadingAgentSkills')}</div>
        ) : promptsData ? (
          <div className="space-y-4">
            {/* Section Selector */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t('section')}</label>
              <select value={selectedSection}
                onChange={(e) => {
                  setSelectedSection(e.target.value);
                  const subsections = Object.keys(promptsData.prompts[e.target.value] || {});
                  if (subsections.length > 0) setSelectedSubsection(subsections[0]);
                }}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                {Object.keys(promptsData.prompts).map((section) => (
                  <option key={section} value={section}>{section.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>

            {/* Subsection Selector */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t('subsection')}</label>
              <select value={selectedSubsection} onChange={(e) => setSelectedSubsection(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500">
                {selectedSection && Object.keys(promptsData.prompts[selectedSection] || {}).map((sub) => (
                  <option key={sub} value={sub}>{sub.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>

            {/* Prompt List */}
            <div className="border-t pt-4 mt-4">
              <h3 className="text-sm font-medium text-slate-700 mb-2">{t('allPrompts')}</h3>
              <div className="max-h-64 overflow-y-auto space-y-1">
                {Object.entries(promptsData.prompts).map(([section, subsections]) => (
                  <div key={section}>
                    <div className="text-xs font-semibold text-slate-500 uppercase mt-2">{section.replace(/_/g, ' ')}</div>
                    {Object.keys(subsections).map((sub) => (
                      <button key={`${section}-${sub}`}
                        onClick={() => { setSelectedSection(section); setSelectedSubsection(sub); }}
                        className={`w-full text-left px-2 py-1 text-sm rounded ${
                          selectedSection === section && selectedSubsection === sub ? 'bg-indigo-100 text-indigo-700' : 'hover:bg-slate-100 text-slate-700'
                        }`}>
                        {sub.replace(/_/g, ' ')}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>

            <button onClick={() => setShowNewPromptForm(true)}
              className="w-full py-2 text-sm text-indigo-600 border border-indigo-300 rounded-lg hover:bg-indigo-50 transition-colors">
              {t('addNewPrompt')}
            </button>
          </div>
        ) : null}
      </div>

      {/* Prompt Editor */}
      <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-slate-900">
            {selectedSection && selectedSubsection
              ? `${selectedSection.replace(/_/g, ' ')} / ${selectedSubsection.replace(/_/g, ' ')}`
              : t('selectPrompt')}
          </h2>
          <div className="flex items-center gap-2">
            <button onClick={onDeletePrompt} disabled={!selectedSection || !selectedSubsection || promptsSaving}
              className="px-3 py-1.5 text-sm text-rose-600 border border-rose-300 rounded-lg hover:bg-rose-50 disabled:opacity-50 transition-colors">
              {t('resetToDefault')}
            </button>
            <button onClick={onSavePrompt} disabled={!selectedSection || !selectedSubsection || promptsSaving}
              className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
              {promptsSaving ? t('saving') : t('save')}
            </button>
          </div>
        </div>

        {promptsError && <div className="mb-4 p-3 bg-rose-50 text-rose-700 rounded-lg text-sm">{promptsError}</div>}
        {promptsSuccess && <div className="mb-4 p-3 bg-emerald-50 text-emerald-700 rounded-lg text-sm">{promptsSuccess}</div>}

        <textarea value={promptText} onChange={(e) => setPromptText(e.target.value)}
          className="w-full h-96 px-4 py-3 border border-slate-300 rounded-lg font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          placeholder={t('selectPromptToEdit')} disabled={!selectedSection || !selectedSubsection} />
        <p className="mt-2 text-xs text-slate-500">{t('promptsHelp')}</p>
      </div>

      {/* New Prompt Modal */}
      {showNewPromptForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold mb-4">{t('createNewPrompt')}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('section')}</label>
                <input type="text" value={newSection} onChange={(e) => setNewSection(e.target.value)} placeholder={tp('promptSection')}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('subsection')}</label>
                <input type="text" value={newSubsection} onChange={(e) => setNewSubsection(e.target.value)} placeholder={tp('promptSubsection')}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t('promptText')}</label>
                <textarea value={newPromptText} onChange={(e) => setNewPromptText(e.target.value)} placeholder={t('promptText')}
                  className="w-full h-40 px-3 py-2 border border-slate-300 rounded-lg font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => { setShowNewPromptForm(false); setNewSection(''); setNewSubsection(''); setNewPromptText(''); }}
                className="px-4 py-2 text-slate-700 hover:bg-slate-100 rounded-lg transition-colors">
                {t('cancel')}
              </button>
              <button onClick={onCreatePrompt} disabled={promptsSaving}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {promptsSaving ? t('creating') : t('createNewPrompt')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
