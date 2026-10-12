/**
 * Pure helpers for the browser-side voice call (VoiceCallModal).
 *
 * Kept free of React / DOM so they can be unit-tested with plain Node:
 *   node --experimental-strip-types --test lib/voiceEndpoint.test.mts
 */

/* ------------------------------------------------------------------ */
/* 1. Adaptive end-of-utterance ("endpointing")                        */
/* ------------------------------------------------------------------ */

/** The fixed wait the modal used before (kept as the "caller is mid-sentence" delay). */
export const ENDPOINT_INCOMPLETE_MS = 1300;
/** Utterance ends in punctuation or looks like a finished sentence. */
export const ENDPOINT_COMPLETE_MS = 600;
/** Utterance is a known one-word answer ("yes", "tomorrow", "9:30" ...). */
export const ENDPOINT_ANSWER_MS = 450;
/** A single unfamiliar word: wait a little longer in case more follows. */
export const ENDPOINT_SINGLE_WORD_MS = 900;
/** Non-Latin scripts: no English heuristics apply, stay conservative. */
export const ENDPOINT_OTHER_SCRIPT_MS = 850;

/** Words that, at the END of an utterance, mean the caller is almost certainly not finished. */
const DANGLING = new Set([
  "a", "an", "the", "and", "or", "but", "so", "if", "because", "to", "for", "of", "in", "on", "at",
  "with", "from", "about", "by", "my", "your", "our", "their", "his", "her", "its", "is", "are", "was",
  "were", "can", "could", "will", "would", "may", "might", "should", "do", "does", "did", "i", "i'd",
  "i'm", "i'll", "we", "you", "that", "this", "what", "when", "where", "how", "who", "which", "than",
  "know", "tell", "want", "wanna", "like", "need", "book", "get", "give", "check", "see", "ask", "find",
  "make", "take", "have", "has", "let", "help",
]);

/** One-word replies that are complete on their own. */
const SHORT_ANSWERS = new Set([
  "yes", "no", "yeah", "yep", "nope", "ok", "okay", "sure", "thanks", "thank", "hello", "hi", "hey",
  "bye", "goodbye", "confirm", "confirmed", "cancel", "correct", "right", "done", "stop", "repeat",
  "please", "tomorrow", "today", "tonight", "morning", "afternoon", "evening",
  "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]);

const isMostlyLatin = (s: string) => {
  const letters = s.match(/\p{L}/gu) || [];
  if (!letters.length) return true; // digits only, e.g. "9:30"
  const latin = letters.filter((c) => /[A-Za-z]/.test(c)).length;
  return latin / letters.length >= 0.8;
};

/**
 * How long to wait after the LAST speech result before treating the utterance as finished.
 * Short when the sentence sounds complete, long when it ends on a dangling word.
 */
export function endpointDelayMs(text: string): number {
  const t = (text || "").trim();
  if (!t) return ENDPOINT_INCOMPLETE_MS;
  if (/[.?!।]$/.test(t)) return ENDPOINT_ANSWER_MS;
  if (!isMostlyLatin(t)) return ENDPOINT_OTHER_SCRIPT_MS;

  const words = t.split(/\s+/);
  const last = words[words.length - 1].toLowerCase().replace(/[^\p{L}\p{N}'’:]/gu, "");
  if (DANGLING.has(last)) return ENDPOINT_INCOMPLETE_MS;
  if (words.length === 1) {
    return SHORT_ANSWERS.has(last) || /\d/.test(last) ? ENDPOINT_ANSWER_MS : ENDPOINT_SINGLE_WORD_MS;
  }
  return ENDPOINT_COMPLETE_MS;
}

/* ------------------------------------------------------------------ */
/* 2. Sticky recognition language                                      */
/* ------------------------------------------------------------------ */

export type LangDecision = { lang: string; candidate: string | null };

/**
 * Decide which language the browser recogniser should listen in next.
 *
 * Why this exists: when the recogniser hears an Indian-accented "no thanks" it can print it in
 * Devanagari/Telugu script. The server then reports "hi"/"te", the recogniser is switched to that
 * language, and every following English sentence is also printed in that script. A single short
 * utterance must therefore not be enough to switch.
 *
 *  - Back to English is accepted from 2+ words (Latin text is reliable evidence).
 *  - A different language needs 4+ words, or the same language twice in a row.
 */
export function nextRecognitionLang(
  current: string,
  detected: string | undefined | null,
  said: string,
  previousCandidate: string | null,
): LangDecision {
  const det = (detected || "").trim().toLowerCase();
  if (!det || det === current) return { lang: current, candidate: null };

  const wordCount = (said || "").trim().split(/\s+/).filter(Boolean).length;
  if (det === "en") {
    return wordCount >= 2 ? { lang: "en", candidate: null } : { lang: current, candidate: null };
  }
  if (wordCount >= 4 || previousCandidate === det) return { lang: det, candidate: null };
  return { lang: current, candidate: det };
}

/* ------------------------------------------------------------------ */
/* 3. Clean downsampling for the specialist (Gemini) microphone feed   */
/* ------------------------------------------------------------------ */

/**
 * Convert float mic samples at `inputRate` to 16-bit PCM at `targetRate` by area-averaging.
 * The old code picked every Nth sample (no low-pass), which folds high frequencies back into the
 * speech band (aliasing) and measurably hurts speech recognition. Averaging each output sample over
 * the input span it covers is a cheap, effective anti-alias filter.
 */
export function downsampleToPcm16(input: Float32Array, inputRate: number, targetRate = 16000): Int16Array {
  const ratio = inputRate / targetRate;
  const outLen = Math.max(1, ratio <= 1 ? input.length : Math.floor(input.length / ratio));
  const out = new Int16Array(outLen);
  const clamp = (v: number) => (v < -1 ? -1 : v > 1 ? 1 : v);

  for (let i = 0; i < outLen; i++) {
    let sample: number;
    if (ratio <= 1) {
      sample = input[Math.min(input.length - 1, Math.floor(i * ratio))] || 0;
    } else {
      const start = i * ratio;
      const end = Math.min(input.length, start + ratio);
      let sum = 0;
      let weight = 0;
      for (let j = Math.floor(start); j < Math.ceil(end); j++) {
        const w = Math.min(j + 1, end) - Math.max(j, start); // overlap of [j, j+1) with [start, end)
        if (w <= 0) continue;
        sum += input[j] * w;
        weight += w;
      }
      sample = weight > 0 ? sum / weight : 0;
    }
    const s = clamp(sample);
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Base64-encode 16-bit PCM for the specialist WebSocket. */
export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, Math.min(i + 0x8000, bytes.length)));
  }
  return btoa(bin);
}
