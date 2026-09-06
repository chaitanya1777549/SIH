import React, { useState, useRef } from 'react';
import { Department, BlockSection, DefectParsePreviewResponse, Severity, MLScorePreview } from '../types';
import { uploadVoiceReport, parseDefectText, createDepartmentDefect, previewDefectScore } from '../api/client';
import { X, Mic, Square, Sparkles, CheckCircle2, MapPin, Clock, RefreshCw } from 'lucide-react';

interface VoiceIntakeModalProps {
  isOpen: boolean;
  onClose: () => void;
  department: Department;
  sections: BlockSection[];
  onDefectCreated: () => void;
}

export const VoiceIntakeModal: React.FC<VoiceIntakeModalProps> = ({
  isOpen,
  onClose,
  department,
  sections,
  onDefectCreated,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState('');
  const [preview, setPreview] = useState<DefectParsePreviewResponse | null>(null);
  const [currentCriticality, setCurrentCriticality] = useState<MLScorePreview | null>(null);
  const [recalculatingScore, setRecalculatingScore] = useState(false);

  // Editable confirmation form state (allows operator override)
  const [selectedSectionId, setSelectedSectionId] = useState<string>('');
  const [defectType, setDefectType] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [severity, setSeverity] = useState<Severity>('medium');
  const [duration, setDuration] = useState<number>(90);
  const [submitting, setSubmitting] = useState(false);
  const [inputMode, setInputMode] = useState<'voice' | 'text'>('voice');
  const [typedText, setTypedText] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<any>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  if (!isOpen) return null;

  // 1. Microphone recording functions
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioUrl(URL.createObjectURL(audioBlob));
        stream.getTracks().forEach((track) => track.stop());
        await processAudio(audioBlob);
      };

      recorder.start();
      setIsRecording(true);
      setRecordSeconds(0);
      setPreview(null);

      timerRef.current = setInterval(() => {
        setRecordSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      alert(`Microphone permission error: ${err.message}. You can also type text or upload an audio file below.`);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(timerRef.current);
    }
  };

  // 2. Process audio via Whisper large-v3 & LLM
  const processAudio = async (blob: Blob) => {
    setLoading(true);
    setLoadingStep('Transcribing speech with Whisper large-v3 & extracting attributes with gpt-oss-120b...');
    try {
      const res = await uploadVoiceReport(blob, 'operator_report.webm', department);
      populateFormFromPreview(res);
    } catch (err: any) {
      alert(`Voice processing failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 3. Process typed text fallback
  const processTypedText = async () => {
    if (!typedText.trim()) return alert('Please enter report text.');
    setLoading(true);
    setLoadingStep('Parsing text with LLM and resolving corridor location...');
    try {
      const res = await parseDefectText(typedText, department);
      populateFormFromPreview(res);
    } catch (err: any) {
      alert(`Parsing failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 4. Populate review fields from AI preview
  const populateFormFromPreview = (data: DefectParsePreviewResponse) => {
    setPreview(data);
    setCurrentCriticality(data.preview_criticality);
    const draft = data.draft_defect;
    setSelectedSectionId(draft.block_section_id);
    setDefectType(draft.defect_type);
    setDescription(draft.description);
    setSeverity(draft.severity);
    setDuration(draft.estimated_duration_min);
  };

  // Live ML score recalculation on section or severity change
  const recalculateScore = async (targetSectionId: string, targetSeverity: Severity) => {
    if (!targetSectionId) return;
    setRecalculatingScore(true);
    try {
      const updated = await previewDefectScore(department, {
        block_section_id: targetSectionId,
        severity: targetSeverity,
        required_by: preview?.draft_defect?.required_by,
        requires_block: true,
        work_category: 'defect',
      });
      setCurrentCriticality(updated);
    } catch (err: any) {
      console.warn('Live score recalculation error:', err);
    } finally {
      setRecalculatingScore(false);
    }
  };

  // 5. Submit confirmed defect into database
  const handleConfirmSubmit = async () => {
    if (!selectedSectionId) return alert('Please select a corridor block section.');
    if (!defectType) return alert('Defect type is required.');

    setSubmitting(true);
    try {
      const shortCode = Math.random().toString(36).substring(2, 7).toUpperCase();
      const code = `${department}-V-${shortCode}`;

      await createDepartmentDefect(department, {
        defect_code: code,
        block_section_id: selectedSectionId,
        defect_type: defectType,
        description: description || 'Voice/NL defect report',
        severity: severity,
        criticality_score: currentCriticality?.predicted_score ?? preview?.preview_criticality?.predicted_score,
        required_by: preview?.draft_defect?.required_by,
        estimated_duration_min: duration,
        work_category: 'defect',
        input_source: 'nl_intake',
        raw_report_text: preview?.raw_text || typedText,
        requires_block: true,
      });

      onDefectCreated();
      onClose();
    } catch (err: any) {
      alert(`Error saving defect into database: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const formatTimer = (s: number) => {
    const mins = String(Math.floor(s / 60)).padStart(2, '0');
    const secs = String(s % 60).padStart(2, '0');
    return `${mins}:${secs}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden my-8">
        {/* Modal Header */}
        <div className="p-4 sm:p-5 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="bg-rose-500/20 text-rose-400 p-2 rounded-xl border border-rose-500/30">
              <Mic className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base flex items-center gap-2">
                Voice & Natural Language Defect Intake
                <span className="text-[10px] bg-blue-500/20 text-blue-400 border border-blue-500/30 px-2 py-0.5 rounded-full font-mono">
                  {department}
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Whisper large-v3 Transcription + gpt-oss-120b Extraction + Corridor Matcher
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 sm:p-6 space-y-6">
          {/* Input Mode Tabs */}
          <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setInputMode('voice')}
              className={`flex-1 py-1.5 rounded-lg font-semibold flex items-center justify-center gap-2 transition ${
                inputMode === 'voice'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Mic className="w-3.5 h-3.5" />
              <span>Voice Recording</span>
            </button>
            <button
              onClick={() => setInputMode('text')}
              className={`flex-1 py-1.5 rounded-lg font-semibold flex items-center justify-center gap-2 transition ${
                inputMode === 'text'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Type Plain Memo</span>
            </button>
          </div>

          {/* Tab 1: Voice Recording Controller */}
          {inputMode === 'voice' && (
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-6 flex flex-col items-center justify-center space-y-4 text-center">
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={loading}
                className={`relative p-6 rounded-full transition-all duration-200 shadow-xl focus:outline-none ${
                  isRecording
                    ? 'bg-red-600 hover:bg-red-700 animate-pulse text-white'
                    : 'bg-rose-600 hover:bg-rose-500 text-white hover:scale-105 shadow-rose-900/40'
                }`}
              >
                {isRecording ? <Square className="w-8 h-8" /> : <Mic className="w-8 h-8" />}
              </button>

              <div className="space-y-1">
                <div className="text-sm font-semibold text-white">
                  {isRecording ? (
                    <span className="text-rose-400 font-bold flex items-center justify-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping"></span>
                      Recording... {formatTimer(recordSeconds)}
                    </span>
                  ) : (
                    'Click to Speak (Push to Record)'
                  )}
                </div>
                <p className="text-xs text-slate-400 max-w-sm">
                  Say: "Severe rail fracture observed near Anakapalle towards Tuni at km 52, needs urgent 90 minute block."
                </p>
              </div>

              {audioUrl && (
                <div className="w-full max-w-sm pt-2">
                  <audio src={audioUrl} controls className="w-full h-8" />
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Typed Text Input */}
          {inputMode === 'text' && (
            <div className="space-y-3">
              <textarea
                value={typedText}
                onChange={(e) => setTypedText(e.target.value)}
                placeholder="Type informal field memo, e.g. Point machine 102 failure at Samalkot junction, technician needs 120 minutes..."
                rows={3}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
              />
              <button
                onClick={processTypedText}
                disabled={loading || !typedText.trim()}
                className="w-full py-2 rounded-xl text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                <span>Parse Memo with AI</span>
              </button>
            </div>
          )}

          {/* Loading Spinner */}
          {loading && (
            <div className="p-6 bg-slate-950/80 border border-slate-800 rounded-xl text-center space-y-3">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-500 border-t-transparent"></div>
              <p className="text-xs font-semibold text-slate-200">{loadingStep}</p>
            </div>
          )}

          {/* Operator Confirmation & Override Card */}
          {preview && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-4 shadow-inner">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>AI Extracted Preview — Review & Adjust</span>
                </span>
                {(currentCriticality || preview.preview_criticality) && (
                  <span className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1.5 transition-all duration-200 border ${
                    recalculatingScore
                      ? 'bg-indigo-500/30 text-indigo-200 border-indigo-400 animate-pulse'
                      : ((currentCriticality?.predicted_score ?? preview.preview_criticality?.predicted_score) || 0) >= 75
                      ? 'bg-red-500/20 text-red-400 border-red-500/30'
                      : ((currentCriticality?.predicted_score ?? preview.preview_criticality?.predicted_score) || 0) >= 50
                      ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                      : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                  }`}>
                    {recalculatingScore ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin text-indigo-300" />
                        <span>Recalculating ML Score...</span>
                      </>
                    ) : (
                      <span>Score: {currentCriticality?.predicted_score ?? preview.preview_criticality.predicted_score}/100</span>
                    )}
                  </span>
                )}
              </div>

              {/* Transcribed Speech snippet */}
              <div className="text-xs bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                <span className="text-slate-400 text-[10px] uppercase font-semibold block mb-0.5">
                  Raw / Transcribed Text:
                </span>
                <span className="text-slate-200 italic font-medium">"{preview.raw_text}"</span>
              </div>

              {/* Form Fields with Operator Dropdown Override */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {/* Corridor Block Section Selector (User Feedback Solution!) */}
                <div className="sm:col-span-2">
                  <label className="block text-slate-300 font-semibold mb-1 flex items-center justify-between">
                    <span className="flex items-center gap-1 text-emerald-400">
                      <MapPin className="w-3.5 h-3.5" />
                      Corridor Block Section (Auto-Matched or Override):
                    </span>
                    <span className="text-[10px] text-slate-500">
                      Method: {preview.location_match.match_method} ({(preview.location_match.confidence * 100).toFixed(0)}%)
                    </span>
                  </label>
                  <select
                    value={selectedSectionId}
                    onChange={(e) => {
                      const newSecId = e.target.value;
                      setSelectedSectionId(newSecId);
                      recalculateScore(newSecId, severity);
                    }}
                    className="w-full bg-slate-900 border border-emerald-500/50 rounded-lg px-3 py-2 text-xs font-mono font-bold text-emerald-300 focus:outline-none focus:border-emerald-400"
                  >
                    {sections.map((s) => (
                      <option key={s.id} value={s.id} className="bg-slate-900 text-slate-200">
                        {s.section_code} ({s.from_station_code} ➔ {s.to_station_code}, {s.length_km} km)
                      </option>
                    ))}
                  </select>
                </div>

                {/* Defect Type */}
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Defect Type:</label>
                  <input
                    type="text"
                    value={defectType}
                    onChange={(e) => setDefectType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                {/* Severity */}
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Severity Level:</label>
                  <select
                    value={severity}
                    onChange={(e) => {
                      const newSev = e.target.value as Severity;
                      setSeverity(newSev);
                      recalculateScore(selectedSectionId, newSev);
                    }}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="critical">Critical (Track isolation)</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>

                {/* Duration */}
                <div>
                  <label className="block text-slate-400 font-medium mb-1 flex items-center gap-1">
                    <Clock className="w-3 h-3 text-amber-400" />
                    Estimated Duration (minutes):
                  </label>
                  <input
                    type="number"
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Technical Description:</label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              {/* ML Criticality Justification & Features Breakdown */}
              {(currentCriticality || preview.preview_criticality) && (
                <div className="space-y-2">
                  <div className={`text-[11px] p-2.5 rounded-lg border transition-all duration-200 ${
                    recalculatingScore
                      ? 'bg-indigo-950/50 border-indigo-500/50 text-indigo-200'
                      : 'bg-indigo-950/30 border-indigo-800/40 text-indigo-200'
                  } leading-snug`}>
                    <div className="flex items-center justify-between mb-1">
                      <strong className="text-indigo-300 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                        Explainable ML Justification (Phase C):
                      </strong>
                      {recalculatingScore && (
                        <span className="text-[10px] text-indigo-400 flex items-center gap-1">
                          <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Recalculating features...
                        </span>
                      )}
                    </div>
                    <p className="text-slate-300">
                      {currentCriticality?.justification ?? preview.preview_criticality.justification}
                    </p>
                  </div>

                  {/* Feature Contributions Breakdown */}
                  {(currentCriticality?.feature_contributions || preview.preview_criticality?.feature_contributions) && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-[10px] font-mono">
                      {Object.entries(currentCriticality?.feature_contributions || preview.preview_criticality?.feature_contributions || {}).map(([feat, pct]) => (
                        <div key={feat} className="bg-slate-900/90 border border-slate-800 rounded px-2 py-1 text-slate-400 flex justify-between items-center">
                          <span className="truncate">{feat.replace(/_/g, ' ')}</span>
                          <span className="text-indigo-300 font-bold ml-1">{typeof pct === 'number' ? `${pct.toFixed(1)}%` : pct}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Submit Button */}
              <div className="pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setPreview(null)}
                  className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white transition"
                >
                  Clear
                </button>
                <button
                  onClick={handleConfirmSubmit}
                  disabled={submitting}
                  className="px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 transition shadow-lg shadow-emerald-900/30 flex items-center gap-2"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{submitting ? 'Committing to Supabase...' : 'Confirm & Insert into Database'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
