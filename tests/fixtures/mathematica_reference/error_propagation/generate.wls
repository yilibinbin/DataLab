#!/usr/bin/env wolframscript
(* Generate symbolic Taylor 1st-order error-propagation reference values.

   For each formula f(x_1, ..., x_n) and each set of (values, sigmas),
   Mathematica computes:
     y       = f(values)
     sigma_y = Sqrt[ Sum_i (D[f, x_i] /. values)^2 * sigma_i^2 ]

   DataLab's ``error_propagation`` with ``method="taylor", order=1``
   should produce the same (y, sigma_y) at 30+ digits.

   The formulas are real-world physics expressions and standard
   teaching cases:
     - linear_combination       y = a*x + b*z
     - product                  y = x*z
     - division                 y = x/z
     - power                    y = x^n
     - quadratic                y = a*x^2 + b*x + c
     - ohms_law_resistance      R = V/I
     - kinetic_energy           E = 1/2 * m * v^2
     - gas_law_PV_to_T          T = P*V/(n*R)        (R = gas const, exact)
*)

DigitString[x_] := Module[{n, rd, digits, expPos, signStr, mantStr, lenDigits},
  n = N[x, 50];
  If[n == 0, Return["0"]];
  signStr = If[n < 0, "-", ""];
  rd = RealDigits[Abs[n], 10, 50];
  If[!ListQ[rd] || Length[rd] != 2 || !ListQ[First[rd]],
    Return["RealDigits-failed-for-" <> ToString[InputForm[x]]]
  ];
  {digits, expPos} = rd;
  lenDigits = Length[digits];
  mantStr = StringJoin[ToString /@ digits];
  Which[
    expPos <= 0, signStr <> "0." <> StringJoin[Table["0", {-expPos}]] <> mantStr,
    expPos >= lenDigits, signStr <> mantStr <> StringJoin[Table["0", {expPos - lenDigits}]],
    True, signStr <> StringTake[mantStr, expPos] <> "." <> StringDrop[mantStr, expPos]
  ]
]

EscapeJsonString[s_] := StringJoin[
  "\"", StringReplace[s, {"\\" -> "\\\\", "\"" -> "\\\""}], "\""
]

JsonNum[x_] := EscapeJsonString[DigitString[x]]
JsonStringList[xs_] := StringJoin["[", StringRiffle[Map[EscapeJsonString, xs], ", "], "]"]
JsonNumList[xs_] := StringJoin["[", StringRiffle[Map[JsonNum, xs], ", "], "]"]

(* ------------------------------------------------------------------ *)
(* TaylorPropagate computes (y, sigma_y) for f at specified rule       *)
(* substitutions with given sigmas. Returns the pair as a list.       *)
(* ------------------------------------------------------------------ *)
(* Compute (y, sigma_y) symbolically, then numericalise to 50 digits.

   Critical hygiene note: the loop variable ``v`` in the original
   implementation collided with the Module local of the same name,
   causing ``D[expr, v]`` inside ``Table`` to use the Module's
   local symbol *as if it were the differentiation variable* — which
   silently produced wrong partial derivatives (e.g. for
   f = (1/2)*m*v^2, ∂f/∂m came out as 6 instead of 50 because the
   inner ``v`` no longer matched the outer ``v`` in ``expr``).

   Renamed the loop variable to ``var`` to break the shadowing.
   Without this fix, ALL expressions whose variable list collides
   with a Module local return wrong sigmas — but only some failed
   loudly (kinetic_energy did; linear_combination's partials were
   constants so the bug didn't bite). *)
TaylorPropagate[expr_, varList_, valuesAssoc_, sigmasAssoc_] := Module[
  {y, varSubs, partials, varianceTerms, sigmaY},
  varSubs = Table[var -> valuesAssoc[var], {var, varList}];
  y = expr /. varSubs;
  partials = Table[D[expr, var] /. varSubs, {var, varList}];
  varianceTerms = Table[partials[[i]]^2 * sigmasAssoc[varList[[i]]]^2,
    {i, Length[varList]}];
  sigmaY = Sqrt[Total[varianceTerms]];
  {N[y, 50], N[sigmaY, 50]}
]

(* ------------------------------------------------------------------ *)
(* Cases as {id, formula-string, varNames, valuesAssoc, sigmasAssoc}   *)
(* The formula-string is in DataLab's Mathematica-flavour syntax       *)
(* (Sin[x], Sqrt[x], x^2, etc.) so the test can hand it directly to   *)
(* DataLab's error_propagation function.                               *)
(* ------------------------------------------------------------------ *)

cases = {
  (* {id, formula, vars, values, sigmas} *)
  {"linear_combination",
   "2*x + 3*z",
   {"x", "z"},
   <|"x" -> 4, "z" -> 5|>,
   <|"x" -> "1/10", "z" -> "1/20"|>},

  {"product",
   "x*z",
   {"x", "z"},
   <|"x" -> 7, "z" -> 11|>,
   <|"x" -> "7/100", "z" -> "11/100"|>},

  {"division",
   "x/z",
   {"x", "z"},
   <|"x" -> 100, "z" -> 4|>,
   <|"x" -> 1, "z" -> "1/10"|>},

  {"square",
   "x^2",
   {"x"},
   <|"x" -> 5|>,
   <|"x" -> "1/2"|>},

  {"quadratic",
   "2*x^2 + 3*x + 1",
   {"x"},
   <|"x" -> 3|>,
   <|"x" -> "1/10"|>},

  (* Note: must NOT use ``I`` (Mathematica's imaginary unit) or ``E``
     (Euler's number) as variable names — they're protected
     constants. Use ``Iv`` for current, ``Ek`` for energy etc. *)
  {"ohms_law_resistance",
   "V/Iv",
   {"V", "Iv"},
   <|"V" -> 12, "Iv" -> 3|>,
   <|"V" -> "1/100", "Iv" -> "1/200"|>},

  {"kinetic_energy",
   "(1/2)*m*v^2",
   {"m", "v"},
   <|"m" -> 2, "v" -> 10|>,
   <|"m" -> "1/100", "v" -> "1/100"|>},

  {"sin_propagation",
   "Sin[x]",
   {"x"},
   <|"x" -> 1|>,
   <|"x" -> "1/100"|>},

  {"exp_decay",
   "Exp[-x/tau]",
   {"x", "tau"},
   <|"x" -> 1, "tau" -> 2|>,
   <|"x" -> "1/100", "tau" -> "1/50"|>},

  {"compound_log",
   "Log[x] + Sqrt[z]",
   {"x", "z"},
   <|"x" -> 7, "z" -> 9|>,
   <|"x" -> "1/100", "z" -> "1/10"|>}
};

(* Coerce string fractions like "1/100" to actual Mathematica
   rationals via ToExpression. Pure numbers pass through. *)
ParseValue[v_] := If[StringQ[v], ToExpression[v], v]

CaseEntry[id_, formula_, vars_, valsAssoc_, sigsAssoc_] := Module[
  {parsedExpr, parsedVars, valuesAssocSym, sigmasAssocSym,
   result, y, sigmaY, valuesList, sigmasList},
  parsedExpr = ToExpression[formula];
  parsedVars = Map[ToExpression, vars];
  (* Build symbol-keyed associations from the string-keyed input.
     The fixture lists sigmas as string fractions ("1/100") to
     preserve exact rationals for Mathematica; ParseValue converts
     them to actual numbers before the partial-derivative arithmetic
     produces a symbolic Sqrt that doesn't numericalise cleanly. *)
  valuesAssocSym = AssociationThread[parsedVars,
    Table[ParseValue[valsAssoc[v]], {v, vars}]];
  sigmasAssocSym = AssociationThread[parsedVars,
    Table[ParseValue[sigsAssoc[v]], {v, vars}]];
  valuesList = Table[ParseValue[valsAssoc[v]], {v, vars}];
  sigmasList = Table[ParseValue[sigsAssoc[v]], {v, vars}];
  result = TaylorPropagate[parsedExpr, parsedVars,
    valuesAssocSym, sigmasAssocSym];
  {y, sigmaY} = result;
  StringJoin[
    "    {",
    "\n      \"id\": ", EscapeJsonString[id], ",",
    "\n      \"formula\": ", EscapeJsonString[formula], ",",
    "\n      \"variables\": ", JsonStringList[vars], ",",
    "\n      \"values\": ", JsonNumList[valuesList], ",",
    "\n      \"sigmas\": ", JsonNumList[sigmasList], ",",
    "\n      \"expected_value\": ", JsonNum[y], ",",
    "\n      \"expected_sigma\": ", JsonNum[sigmaY],
    "\n    }"
  ]
]

caseLines = Map[CaseEntry @@ # &, cases];

metadata = StringJoin[
  "  \"metadata\": {",
  "\n    \"generator\": \"tests/fixtures/mathematica_reference/error_propagation/generate.wls\",",
  "\n    \"mathematica_version\": ", EscapeJsonString[ToString[$Version]], ",",
  "\n    \"precision_digits\": 50,",
  "\n    \"order\": \"taylor_1st\",",
  "\n    \"description\": \"Symbolic Taylor 1st-order error propagation reference values.\"",
  "\n  }"
];

casesJson = StringJoin[
  "  \"cases\": [\n",
  StringRiffle[caseLines, ",\n"],
  "\n  ]"
];

Print["{"];
Print[metadata, ","];
Print[casesJson];
Print["}"];
