// Run: node --experimental-strip-types --test lib/voiceEndpoint.test.mts
import test from "node:test";
import assert from "node:assert/strict";
import {
  ENDPOINT_ANSWER_MS,
  ENDPOINT_COMPLETE_MS,
  ENDPOINT_INCOMPLETE_MS,
  ENDPOINT_OTHER_SCRIPT_MS,
  ENDPOINT_SINGLE_WORD_MS,
  downsampleToPcm16,
  endpointDelayMs,
  nextRecognitionLang,
} from "./voiceEndpoint.ts";

test("complete sentences are sent quickly, mid-sentence fragments wait the old 1.3 s", () => {
  assert.equal(endpointDelayMs("what are your timings"), ENDPOINT_COMPLETE_MS);
  assert.equal(endpointDelayMs("may I know the timings"), ENDPOINT_COMPLETE_MS);
  assert.equal(endpointDelayMs("may I know"), ENDPOINT_INCOMPLETE_MS);
  assert.equal(endpointDelayMs("I want to book an"), ENDPOINT_INCOMPLETE_MS);
  assert.equal(endpointDelayMs("and"), ENDPOINT_INCOMPLETE_MS);
  assert.equal(endpointDelayMs(""), ENDPOINT_INCOMPLETE_MS);
});

test("one-word answers, times and punctuation end quickly", () => {
  for (const w of ["yes", "No", "tomorrow", "9:30", "confirm", "Monday", "ok"]) {
    assert.equal(endpointDelayMs(w), ENDPOINT_ANSWER_MS, w);
  }
  assert.equal(endpointDelayMs("No thanks."), ENDPOINT_ANSWER_MS);
  assert.equal(endpointDelayMs("what is the fee?"), ENDPOINT_ANSWER_MS);
  assert.equal(endpointDelayMs("manoj"), ENDPOINT_SINGLE_WORD_MS);
});

test("non-Latin scripts get a conservative fixed delay", () => {
  assert.equal(endpointDelayMs("नो थैंक्स"), ENDPOINT_OTHER_SCRIPT_MS);
  assert.equal(endpointDelayMs("నో థాంక్స్"), ENDPOINT_OTHER_SCRIPT_MS);
});

test("every 'sounds finished' delay is shorter than the old fixed 1300 ms", () => {
  for (const d of [ENDPOINT_ANSWER_MS, ENDPOINT_COMPLETE_MS, ENDPOINT_SINGLE_WORD_MS, ENDPOINT_OTHER_SCRIPT_MS]) {
    assert.ok(d < ENDPOINT_INCOMPLETE_MS);
  }
});

test("a single short Devanagari/Telugu result does not switch the recogniser language", () => {
  const first = nextRecognitionLang("en", "hi", "नो थैंक्स", null);
  assert.deepEqual(first, { lang: "en", candidate: "hi" });
  // the same language twice in a row is accepted (a genuine Hindi speaker)
  assert.deepEqual(nextRecognitionLang("en", "hi", "हाँ जी", first.candidate), { lang: "hi", candidate: null });
  // a long utterance switches immediately
  assert.equal(nextRecognitionLang("en", "te", "నాకు రేపు అపాయింట్‌మెంట్ కావాలి", null).lang, "te");
});

test("recogniser returns to English from 2+ Latin words, not from one", () => {
  assert.equal(nextRecognitionLang("hi", "en", "no thanks", null).lang, "en");
  assert.equal(nextRecognitionLang("hi", "en", "yes", null).lang, "hi");
  assert.deepEqual(nextRecognitionLang("en", "en", "hello there", "hi"), { lang: "en", candidate: null });
  assert.deepEqual(nextRecognitionLang("en", undefined, "hello there", null), { lang: "en", candidate: null });
});

const rms = (a: Int16Array) => Math.sqrt(a.reduce((s, v) => s + (v / 32768) ** 2, 0) / a.length);
const tone = (hz: number, rate: number, seconds: number) =>
  Float32Array.from({ length: Math.floor(rate * seconds) }, (_, i) => 0.5 * Math.sin((2 * Math.PI * hz * i) / rate));

test("downsample 48k -> 16k keeps length and keeps in-band speech", () => {
  const out = downsampleToPcm16(tone(440, 48000, 1), 48000);
  assert.equal(out.length, 16000);
  assert.ok(rms(out) > 0.3 && rms(out) < 0.4); // 0.5 amplitude sine -> RMS ~0.354
});

test("downsample 44.1k -> 16k handles the fractional ratio", () => {
  const out = downsampleToPcm16(tone(440, 44100, 1), 44100);
  assert.ok(Math.abs(out.length - 16000) <= 1);
  assert.ok(rms(out) > 0.3 && rms(out) < 0.4);
});

test("out-of-band energy is attenuated instead of aliasing at full strength", () => {
  // a 12 kHz tone is above the 8 kHz Nyquist limit of 16 kHz audio.
  const src = tone(12000, 48000, 1);
  const naive = Int16Array.from({ length: 16000 }, (_, i) => src[i * 3] * 32767); // the old "pick every 3rd sample"
  const averaged = downsampleToPcm16(src, 48000);
  assert.ok(rms(averaged) < rms(naive) * 0.6, `averaged ${rms(averaged)} vs naive ${rms(naive)}`);
});

test("silence and clipping stay within range", () => {
  assert.ok(downsampleToPcm16(new Float32Array(480), 48000).every((v) => v === 0));
  const loud = downsampleToPcm16(Float32Array.from({ length: 480 }, () => 5), 48000);
  assert.ok(loud.every((v) => v === 32767));
});
