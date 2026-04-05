export function inferLanguage(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase();
  if (!ext) return 'plaintext';

  const langMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    py: 'python',
    md: 'markdown',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    html: 'html',
    css: 'css',
    scss: 'scss',
    sass: 'sass',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    sql: 'sql',
    go: 'go',
    rs: 'rust',
    java: 'java',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    hpp: 'cpp',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    kt: 'kotlin',
    xml: 'xml',
    toml: 'toml',
    ini: 'ini',
    conf: 'conf',
    txt: 'plaintext',
  };

  return langMap[ext] || 'plaintext';
}
