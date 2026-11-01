import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "recorded" | "unsupported" | "denied";
const MAX_SECONDS = 60;

/** MediaRecorder wrapper for the storekeeper remark (audio/webm where the browser supports it). */
export function useVoiceRecorder() {
  const supported = typeof window !== "undefined" && typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
  const [state, setState] = useState<RecorderState>(supported ? "idle" : "unsupported");
  const [seconds, setSeconds] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const release = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const stop = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (!supported) return;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = media;
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
      const rec = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.current.push(e.data); };
      rec.onstop = () => {
        const type = rec.mimeType || mime || "audio/webm";
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunks.current, { type });
        release();
        if (blob.size === 0) { setState("idle"); return; }
        setFile(new File([blob], `remark.${ext}`, { type }));
        setState("recorded");
      };
      recorder.current = rec;
      setSeconds(0);
      setFile(null);
      rec.start();
      setState("recording");
      const startedAt = Date.now();
      timer.current = setInterval(() => {
        const s = Math.floor((Date.now() - startedAt) / 1000);
        setSeconds(s);
        if (s >= MAX_SECONDS) stop();
      }, 250);
    } catch {
      release();
      setState("denied");
    }
  }, [supported, release, stop]);

  const remove = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") {
      recorder.current.onstop = null;
      recorder.current.stop();
    }
    release();
    setFile(null);
    setSeconds(0);
    setState(supported ? "idle" : "unsupported");
  }, [release, supported]);

  useEffect(() => remove, [remove]);

  return { state, seconds, file, start, stop, remove, maxSeconds: MAX_SECONDS };
}

export const formatClock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
