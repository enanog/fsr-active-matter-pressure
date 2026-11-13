function s = texto_tex(s)
% TEXTO_TEX  Escape the underscores of measurement codes for TeX text (legends, titles, tick labels):
% '20261030_1200_22AL_60' -> '20261030\_1200\_22AL\_60'. Subscripts written as _{...} and underscores
% already escaped are kept, so custom labels like 'V_{media}' still work. Accepts char or cell.
    s = regexprep(s, '(?<!\\)_(?!\{)', '\\_');
end
