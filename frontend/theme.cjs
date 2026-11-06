const plugin = require('tailwindcss/plugin');
const colors = require('tailwindcss/colors');

const neutral = {
  surface: '#14243a',
  canvas: '#0c1625',
  text: '#edf3fb',
  muted: '#b8c7d9',
  border: '#627a95',
};
const neutralBackgrounds = {
  50: '#101e30', 100: '#192c43', 200: '#243c55', 300: '#304c68',
  400: '#304c68', 500: '#304c68', 600: '#24486c', 700: '#17395c',
  800: '#102f4c', 900: '#091d30', 950: '#071321',
};
const neutralText = {
  50: '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#d3dfed',
  400: neutral.muted, 500: '#afc0d4', 600: '#c4d2e3', 700: '#d6e1ef',
  800: '#e3edf8', 900: neutral.text, 950: '#f7fbff',
};
const neutralNames = new Set(['slate', 'gray', 'zinc', 'neutral', 'stone']);
const opacitySteps = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95, 100];

function rgb(hex) {
  return hex.replace('#', '').match(/../g).map(value => parseInt(value, 16));
}
function mix(left, right, weight) {
  return '#' + rgb(left).map((value, index) =>
    Math.round(value * (1 - weight) + rgb(right)[index] * weight).toString(16).padStart(2, '0')
  ).join('');
}
function contrast(left, right) {
  const luminance = hex => rgb(hex).map(value => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  const values = [luminance(left), luminance(right)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
function palette(name, shades) {
  const isNeutral = neutralNames.has(name);
  const solid = contrast(shades[700], '#ffffff') >= 4.5 ? shades[700] : shades[800];
  return Object.fromEntries(Object.entries(shades).map(([shade, original]) => [
    shade,
    {
      lightBackground: Number(shade) >= 500 && Number(shade) <= 600 ? solid : original,
      lightText: isNeutral ? Number(shade) >= 300 && Number(shade) <= 500 ? colors.slate[600] : original
        : Number(shade) >= 400 && Number(shade) <= 700 ? shades[800] : original,
      background: isNeutral ? neutralBackgrounds[shade] : Number(shade) < 400
        ? mix(neutral.canvas, shades[700], 0.22)
        : shades[Number(shade) >= 800 ? 950 : 800],
      text: isNeutral ? neutralText[shade] : mix(shades[200], '#ffffff', 0.18),
      border: isNeutral ? neutral.border : shades[400],
    },
  ]));
}

const palettes = Object.fromEntries([
  ...neutralNames,
  'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal',
  'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose',
].map(name => [name, palette(name, colors[name])]));

const themePlugin = plugin(({ addUtilities, e, theme }) => {
  const rules = {};
  const scope = mode => `html[data-app-theme="${mode}"] &:not(:where([data-theme-static], [data-theme-static] *))`;
  const declare = (utility, light, dark) => {
    rules[`.${e(utility)}`] = {
      '@media screen': {
        ...(light && { [scope('light')]: light }),
        [scope('dark')]: dark,
      },
    };
  };
  const alpha = (hex, opacity) => `rgb(${rgb(hex).join(' ')} / ${opacity / 100})`;
  const gradients = (prefix, value) => prefix === 'via'
    ? { '--tw-gradient-stops': `var(--tw-gradient-from), ${value} var(--tw-gradient-via-position), var(--tw-gradient-to)` }
    : { [`--tw-gradient-${prefix}`]: `${value} var(--tw-gradient-${prefix}-position)` };
  for (const [name, shades] of Object.entries(palettes)) {
    for (const [shade, values] of Object.entries(shades)) {
      const key = `${name}-${shade}`;
      declare(`text-${key}`, values.lightText && { color: values.lightText }, { color: values.text });
      declare(`border-${key}`, null, { borderColor: values.border });
      declare(`divide-${key}`, null, { '& > :not([hidden]) ~ :not([hidden])': { borderColor: values.border } });
      declare(`ring-${key}`, null, { '--tw-ring-color': values.border });
      declare(`placeholder-${key}`, { '&::placeholder': { color: values.lightText } }, { '&::placeholder': { color: values.text } });
      for (const opacity of [null, ...opacitySteps]) {
        const suffix = opacity === null ? '' : `/${opacity}`;
        const background = opacity === null ? values.background : alpha(values.background, opacity);
        const lightBackground = opacity === null ? values.lightBackground : alpha(values.lightBackground, opacity);
        declare(`bg-${key}${suffix}`, null, { backgroundColor: background });
        for (const prefix of ['from', 'via', 'to']) {
          declare(`${prefix}-${key}${suffix}`, null, gradients(prefix, background));
        }
        if (Number(shade) >= 500 && Number(shade) <= 600 && !neutralNames.has(name)) {
          rules[`.${e(`bg-${key}${suffix}`)}`]['@media screen'][scope('light')] = { backgroundColor: lightBackground };
        }
      }
    }
  }
  for (const opacity of [null, ...opacitySteps]) {
    const suffix = opacity === null ? '' : `/${opacity}`;
    const surface = opacity === null ? neutral.surface : alpha(neutral.surface, opacity);
    declare(`bg-white${suffix}`, null, { backgroundColor: surface });
    for (const prefix of ['from', 'via', 'to']) declare(`${prefix}-white${suffix}`, null, gradients(prefix, surface));
  }
  for (const [name, shades] of Object.entries({ primary: theme('colors.primary') })) {
    for (const [shade, color] of Object.entries(shades)) {
      declare(`text-${name}-${shade}`, null, { color: mix(color, '#ffffff', 0.75) });
      declare(`bg-${name}-${shade}`, null, { backgroundColor: Number(shade) < 400 ? neutralBackgrounds[100] : color });
      declare(`border-${name}-${shade}`, null, { borderColor: neutral.border });
    }
  }
  declare('text-brand-primary', null, { color: '#b7d9f7' });
  declare('text-brand-accent', null, { color: '#b7d9f7' });
  addUtilities(rules);
});

module.exports = { themePlugin, neutral, palettes, contrast };
