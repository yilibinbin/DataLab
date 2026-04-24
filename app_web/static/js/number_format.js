/**
 * DataLab Web - High precision number formatting
 *
 * Display rules (desktop + web aligned):
 * - When scientific notation is OFF: `digits` means decimal places.
 * - When scientific notation is ON:  `digits` means significant digits (and output is scientific notation).
 *
 * Implementation avoids `Number(...)` (IEEE-754 double) and formats by string arithmetic.
 *
 * Exposes: globalThis.DLNumberFormat.formatNumber(raw, digits, sci)
 */

(function initNumberFormat(root) {
  'use strict';

  const target = root || (typeof globalThis !== 'undefined' ? globalThis : {});

  function isDigit(ch) {
    return ch >= '0' && ch <= '9';
  }

  function incrementDecimalString(digits) {
    const arr = digits.split('');
    let carry = 1;
    for (let i = arr.length - 1; i >= 0; i--) {
      if (!carry) break;
      const d = arr[i].charCodeAt(0) - 48 + carry;
      if (d >= 10) {
        arr[i] = '0';
        carry = 1;
      } else {
        arr[i] = String.fromCharCode(48 + d);
        carry = 0;
      }
    }
    if (carry) arr.unshift('1');
    return arr.join('');
  }

  function parseNumberString(raw) {
    const s = String(raw ?? '').trim();
    if (!s) return null;
    const lower = s.toLowerCase();
    if (lower === 'nan' || lower === 'inf' || lower === '+inf' || lower === '-inf' || lower === 'infinity' || lower === '+infinity' || lower === '-infinity') {
      return null;
    }

    const m = s.match(/^([+-])?(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
    if (!m) return null;

    const sign = m[1] === '-' ? '-' : '';
    const base = m[2] || '0';
    const expPart = m[3] || '0';
    let exp = parseInt(expPart, 10);
    if (!Number.isFinite(exp)) exp = 0;

    const dotIdx = base.indexOf('.');
    let intPart = base;
    let fracPart = '';
    if (dotIdx >= 0) {
      intPart = base.slice(0, dotIdx);
      fracPart = base.slice(dotIdx + 1);
    }

    // Drop leading zeros in coefficient digits.
    let digits = (intPart + fracPart).replace(/^0+/, '');
    if (!digits) digits = '0';

    // exp10 is the power of 10 applied to the integer coefficient.
    // value = digits * 10^(exp10)
    const exp10 = exp - fracPart.length;
    return { sign, digits, exp10 };
  }

  function roundToSignificant(parsed, sigDigits) {
    const d = Math.max(0, sigDigits | 0);
    if (!parsed || !parsed.digits) return null;
    if (parsed.digits === '0') return { digits: '0', exp10: 0 };
    if (d === 0) return null;

    const digits = parsed.digits;
    const L = digits.length;
    let coeff = digits;
    let exp10 = parsed.exp10;

    if (L >= d) {
      exp10 = parsed.exp10 + (L - d);
      coeff = digits.slice(0, d);
      const nextDigit = digits[d];
      if (nextDigit && isDigit(nextDigit) && nextDigit >= '5') {
        coeff = incrementDecimalString(coeff);
        if (coeff.length > d) {
          exp10 += 1;
          coeff = coeff.slice(0, d);
        }
      }
    } else {
      const pad = d - L;
      coeff = digits + '0'.repeat(pad);
      exp10 = parsed.exp10 - pad;
    }

    // Normalize any accidental leading zeros (shouldn't happen for nonzero).
    coeff = coeff.replace(/^0+/, '');
    if (!coeff) return { digits: '0', exp10: 0 };

    return { digits: coeff, exp10 };
  }

  function formatPlain(sign, coeff, exp10) {
    if (!coeff || coeff === '0') return '0';
    const pos = coeff.length + exp10;
    if (pos <= 0) {
      return `${sign}0.${'0'.repeat(-pos)}${coeff}`;
    }
    if (pos >= coeff.length) {
      return `${sign}${coeff}${'0'.repeat(pos - coeff.length)}`;
    }
    return `${sign}${coeff.slice(0, pos)}.${coeff.slice(pos)}`;
  }

  function formatSci(sign, coeff, exp10) {
    if (!coeff || coeff === '0') return '0';
    const mantissa = coeff.length > 1 ? `${coeff[0]}.${coeff.slice(1)}` : coeff;
    const expSci = exp10 + (coeff.length - 1);
    const expSign = expSci >= 0 ? '+' : '-';
    return `${sign}${mantissa}e${expSign}${Math.abs(expSci)}`;
  }

  function roundToNearestIntegerAbs(digits, exp10) {
    if (!digits || digits === '0') return '0';
    if (exp10 >= 0) {
      return `${digits}${'0'.repeat(exp10)}`;
    }
    const pos = digits.length + exp10;
    if (pos < 0) {
      // Decimal point is before the first digit with at least one leading 0 after '.', so |value| < 0.1 < 0.5
      return '0';
    }
    if (pos === 0) {
      // 0.<digits>
      return (digits[0] || '0') >= '5' ? '1' : '0';
    }
    if (pos >= digits.length) {
      return digits;
    }
    let intPart = digits.slice(0, pos);
    const roundDigit = digits[pos] || '0';
    if (roundDigit >= '5') {
      intPart = incrementDecimalString(intPart);
    }
    intPart = intPart.replace(/^0+/, '');
    return intPart || '0';
  }

  function formatFixedDecimals(parsed, places) {
    if (!parsed || !parsed.digits) return null;
    const p = Math.max(0, places | 0);
    if (parsed.digits === '0') {
      return p === 0 ? '0' : `0.${'0'.repeat(p)}`;
    }
    const scaledExp10 = parsed.exp10 + p;
    const scaledRounded = roundToNearestIntegerAbs(parsed.digits, scaledExp10);
    if (scaledRounded === '0') {
      // Avoid -0.000... in display
      return p === 0 ? '0' : `0.${'0'.repeat(p)}`;
    }
    const sign = parsed.sign;
    if (p === 0) {
      return `${sign}${scaledRounded}`;
    }
    const L = scaledRounded.length;
    if (L <= p) {
      return `${sign}0.${'0'.repeat(p - L)}${scaledRounded}`;
    }
    return `${sign}${scaledRounded.slice(0, L - p)}.${scaledRounded.slice(L - p)}`;
  }

  function formatNumber(raw, digits, sci) {
    if (raw === undefined || raw === null || raw === '') return raw;
    const parsed = parseNumberString(raw);
    if (!parsed) return raw;

    let d = parseInt(String(digits ?? ''), 10);
    if (!Number.isFinite(d)) d = 10;

    if (!sci) {
      // Decimal places mode
      const places = Math.max(0, d | 0);
      const fixed = formatFixedDecimals(parsed, places);
      return fixed == null ? raw : fixed;
    }

    // Significant digits mode (scientific notation)
    const sigDigits = Math.max(1, d | 0);
    const rounded = roundToSignificant(parsed, sigDigits);
    if (!rounded) return raw;
    if (rounded.digits === '0') return '0';
    return formatSci(parsed.sign, rounded.digits, rounded.exp10);
  }

  target.DLNumberFormat = Object.freeze({
    formatNumber,
  });
})(typeof window !== 'undefined' ? window : undefined);
