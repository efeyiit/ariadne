import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
export type Language = 'en' | 'tr';
const key = 'ariadne:language';
export function initialLanguage(saved: string | null): Language { return saved === 'tr' ? 'tr' : 'en'; }
const tr: Record<string, string> = {
 'Open source':'Kaynağı aç', 'source nodes':'kaynak düğümü', 'relationships':'ilişki', 'cycles':'döngü', 'file':'dosya', 'symbol':'sembol',
 'SELECTED SOURCE NODE':'SEÇİLİ KAYNAK DÜĞÜMÜ', 'Select a graph node to inspect and open its source.':'Kaynağını incelemek için bir düğüm seç.',
 'Critical nodes':'Merkezi düğümler', 'Graph nodes':'Graf düğümleri', 'Open a node’s source at this commit':'İncelenen sürümde düğümün kaynağını aç',
 'Resolved, ambiguous, and external edges are labeled':'Çözümlenen, belirsiz ve dış bağlantılar işaretlidir', 'Unknown source':'Bilinmeyen kaynak',
 'External target':'Dış hedef', 'Unresolved target':'Çözümlenemeyen hedef', 'Candidates:':'Adaylar:', 'Circular dependencies':'Döngüsel bağımlılıklar',
 'No dependency relationships were returned.':'Bağımlılık ilişkisi bulunamadı.', 'No dependencies in this snapshot':'Bu kopyada bağımlılık yok',
 'The report returned an empty dependency graph.':'Raporda bağımlılık grafı boş.', 'resolved':'çözümlendi', 'external':'dış', 'ambiguous':'belirsiz',
 'import':'içe aktarım', 'call':'çağrı', 'inheritance':'kalıtım', 'Rendering Mermaid preview locally…':'Diyagram yerel olarak çiziliyor…',
 'Mermaid could not safely render this diagram. The source remains available.':'Diyagram güvenli biçimde çizilemedi. Kaynak verileri kullanılabilir.',
 'Local AI is not available. Static analysis remains usable.':'Yerel AI kullanılamıyor. Statik analiz kullanılabilir.',
 'No source evidence is available for this snapshot.':'Bu kaynak kopyası için kanıt bulunamadı.',
 'The model did not find enough source evidence to answer this question.':'Model bu soruyu yanıtlamak için yeterli kaynak bulamadı.',
 'The model response could not be verified against the selected source.':'Model yanıtı seçili kaynakla doğrulanamadı.',
 'Answer belongs to another snapshot.':'Yanıt başka bir kaynak kopyasına ait.', 'Report belongs to a different source snapshot.':'Rapor farklı bir kaynak kopyasına ait.',
 'SOURCE_NOT_FOUND':'Kaynak dosyası bulunamadı.', 'REPORT_NOT_FOUND':'Rapor bulunamadı.', 'REPOSITORY_NOT_FOUND':'Depo bulunamadı.',
 'ANALYSIS_FAILED':'Analiz tamamlanamadı.', 'INTERRUPTED':'Analiz uygulama kapanınca kesildi.', 'INVALID_INPUT':'Gönderilen bilgileri kontrol et.',
 'commit':'commit', 'snapshot':'kaynak kopyası',

  'Workspace':'Çalışma alanı', 'Repositories':'Depolar', 'Skip to content':'İçeriğe geç',
  'Saved repositories':'Kayıtlı depolar', 'Public GitHub':'Herkese açık GitHub', 'Local source':'Yerel kaynak',
  'On your computer':'Bu bilgisayarda', 'No account required':'Hesap gerekmez', 'Opening your workspace…':'Çalışma alanı açılıyor…',
  'Take a look around':'Projenin içini', 'your project.':'birlikte inceleyelim.',
  'Bring in a repository to explore its files, see what connects them,':'Dosyaları ve aralarındaki bağlantıları incelemek,',
  'and find the parts that could use some attention.':'iyileştirilebilecek yerleri bulmak için bir depo ekle.',
  'Explore':'Keşfet', 'Understand':'Anla', 'Follow':'İzle', 'Further':'İlerle',
  'What are you working on?':'Hangi projeyi inceleyelim?', 'Project source':'Proje kaynağı', 'GitHub repository':'GitHub deposu',
  'Folder on this computer':'Bu bilgisayardaki klasör', 'Paste a public repository link to get started.':'Başlamak için herkese açık bir depo bağlantısı yapıştır.',
  'GitHub repository URL':'GitHub depo bağlantısı', 'Importing…':'İçe aktarılıyor…', 'Open repository':'Depoyu aç',
  'Choose a project folder, including a private repository.':'Özel depon da dahil, bir proje klasörü seç.',
  'Your repositories':'Depoların', 'Search repositories':'Depolarda ara', 'Find a repository…':'Depo ara…',
  'Public GitHub repository':'Herkese açık GitHub deposu', 'Local source folder':'Yerel kaynak klasörü',
  'No matching repositories':'Eşleşen depo yok', 'No projects yet':'Henüz proje yok', 'Try a different repository name.':'Başka bir depo adı dene.',
  'Import a GitHub repository or choose a source folder above.':'Yukarıdan GitHub deposu veya kaynak klasörü ekle.', 'Clear search':'Aramayı temizle',
  'Explore your code':'Kodunu keşfet', 'Projects are saved on this computer.':'Projeler bu bilgisayarda saklanır.',
  'Overview':'Genel bakış', 'Files':'Dosyalar', 'Architecture':'Mimari', 'Dependencies':'Bağımlılıklar', 'Findings':'Bulgular',
  'Security':'Güvenlik', 'Testing':'Testler', 'Refactoring':'İyileştirmeler', 'Documentation':'Dokümantasyon', 'AI chat':'AI sohbeti',
  'PUBLIC GITHUB REPOSITORY':'HERKESE AÇIK GITHUB DEPOSU', 'LOCAL SOURCE SNAPSHOT':'YEREL KAYNAK KOPYASI',
  'Saved on this computer':'Bu bilgisayarda kayıtlı', 'Analyzing…':'Analiz ediliyor…', 'Analyze snapshot':'Yeniden analiz et', 'Run analysis':'Analizi başlat',
  'Analysis:':'Analiz:', 'Cancel':'İptal et', 'Repository analysis views':'Depo analiz bölümleri', 'Saved analysis':'Kayıtlı analiz',
  'Loading saved sources…':'Kayıtlı kaynaklar yükleniyor…', 'Excluded files':'Dışarıda bırakılan dosyalar',
  'Ready to explore this codebase':'Kod tabanı incelenmeye hazır', 'Run an analysis to see the structure, dependencies and findings. Each finding links back to the code.':'Yapıyı, bağımlılıkları ve bulguları görmek için analizi başlat. Her bulgudan ilgili koda ulaşabilirsin.',
  'Reading folder…':'Klasör okunuyor…', 'Import updated folder':'Güncel klasörü aktar', 'Choose a source folder':'Kaynak klasörü seç',
  'Saving source snapshot…':'Kaynak kopyası kaydediliyor…', 'Folder import failed.':'Klasör aktarılamadı.',
  'Your files stay on this computer. Keys, environment files and dependency folders are skipped.':'Dosyaların bu bilgisayarda kalır. Anahtarlar, ortam dosyaları ve bağımlılık klasörleri alınmaz.',
  'Ask about the code':'Kod hakkında sor', 'Ask about a function or file. The local model answers from matching code and links to the source. It may miss context from other parts of the project.':'Bir fonksiyon veya dosya hakkında sor. Yerel model ilgili koddan yanıt üretir ve kaynağı gösterir. Projenin başka bölümlerindeki bağlamı kaçırabilir.',
  'Local AI is not connected or is still loading. Static analysis works independently.':'Yerel AI bağlı değil veya yükleniyor. Statik analiz bağımsız çalışır.',
  'Check again':'Tekrar kontrol et', 'Your question':'Sorun', 'Ask local AI':'Yerel AI’a sor', 'Checking source evidence…':'Kaynak inceleniyor…',
  'Dark mode':'Koyu tema', 'Dark mode is on':'Koyu tema açık', 'Light mode is on':'Açık tema açık', 'Source code':'Kaynak kod',
  'succeeded':'tamamlandı', 'running':'çalışıyor', 'queued':'sırada', 'failed':'başarısız', 'partial':'kısmen tamamlandı', 'cancelled':'iptal edildi',
  'answered':'yanıtlandı', 'no_evidence':'yeterli kaynak yok', 'unavailable':'kullanılamıyor', 'rejected':'doğrulanamadı', 'not_requested':'istenmedi',
  'architect':'mimari', 'security':'güvenlik', 'testing':'testler', 'refactoring':'iyileştirme', 'documentation':'dokümantasyon',
  'high':'yüksek', 'medium':'orta', 'low':'düşük', 'critical':'kritik', 'info':'bilgi', 'static':'statik', 'deterministic':'kural tabanlı',
  'Assessment:':'Değerlendirme:', 'supported':'destekleniyor', 'mixed':'karma', 'insufficient':'yetersiz', 'unknown':'bilinmiyor',
  'Coverage:':'Test kapsamı:', 'No coverage artifact supplied. Tests were not executed.':'Kapsam raporu yok. Testler çalıştırılmadı.',
  'Test files':'Test dosyaları', 'No test files detected.':'Test dosyası bulunamadı.', 'Service observations':'Servis gözlemleri', 'No linked test files.':'Bağlantılı test dosyası bulunamadı.',
  'Source-backed drafts. Review before using them as project documentation.':'Kaynağa dayalı taslaklar. Proje belgesi olarak kullanmadan önce incele.', 'README draft':'README taslağı', 'API draft':'API taslağı',
  'Documentation analysis is unavailable.':'Dokümantasyon analizi yok.', 'No supported refactoring candidates were found.':'Kaynakla desteklenen iyileştirme adayı bulunamadı.',
  'No findings were returned for this view. This does not establish that the code is free of defects.':'Bu bölümde bulgu yok. Bu, kodun hatasız olduğu anlamına gelmez.',
  'Potential security issue. Inspect the linked source; sensitive text is withheld from this summary.':'Olası güvenlik sorunu. Bağlantılı kaynağı incele; hassas metin bu özette gösterilmez.',
  'Source nodes':'Kaynak düğümleri', 'Relationships':'İlişkiler', 'Analysis roles':'Analiz adımları', 'Download full analysis':'Raporu indir',
  'These are deterministic source analyses. AI explanations are not connected to this report.':'Bu eski rapor yalnızca statik analiz içeriyor. Yeni depo raporu için yeniden analiz et.',
  'Dependency analysis is unavailable.':'Bağımlılık analizi yok.', 'Project review':'Depo analizi', 'What this project does':'Proje ne yapıyor?',
  'Start reading here':'İncelemeye buradan başla', 'Important modules':'Önemli modüller', 'What to fix first':'Önce neyi düzeltmeli?',
  'How the parts connect':'Parçalar nasıl bağlanıyor?', 'Analysis scope':'Analizin kapsamı', 'Read the project README':'Projenin README dosyasını aç',
  'The model could not produce a source-backed explanation.':'Model kaynakla desteklenen bir açıklama üretemedi.',
  'No explicit entry point found.':'Açık bir giriş noktası bulunamadı.', 'Entry point candidates from declarations; runtime paths were not executed.':'Bildirimlerden bulunan giriş noktası adaylarıdır; çalışma yolları yürütülmedi.',
  'Source declarations':'Kaynak bildirimleri', 'No parsed modules. Check excluded files and supported languages.':'Ayrıştırılan modül yok. Dışlanan dosyaları ve desteklenen dilleri kontrol et.',
  'No rule findings. This is not a clean bill of health.':'Kural bulgusu yok. Bu, projenin sorunsuz olduğunu göstermez.',
  'Inspect the linked code and its callers before changing it.':'Değiştirmeden önce ilgili kodu ve çağıran yerleri incele.',
  'Local AI explanation':'Yerel AI açıklaması', 'Static evidence':'Statik kanıt', 'Report language':'Rapor dili',
  'Run analysis again to generate explanations in the selected language.':'Açıklamaları seçili dilde üretmek için analizi yeniden çalıştır.',
  'Source links verify location, not whether a model interpretation is correct.':'Kaynak bağlantıları konumu doğrular; model yorumunun doğruluğunu garanti etmez.',
  'Source files':'Kaynak dosyalar', 'Parsed files':'Ayrıştırılan dosyalar', 'Explained modules':'Açıklanan modüller',
  'Show static findings':'Statik bulguları göster', 'Original analyzer detail':'Analiz aracının özgün ayrıntısı',
  'The request failed.':'İstek başarısız oldu.', 'The request could not be completed.':'İstek tamamlanamadı.',
  'AI request failed.':'AI isteği başarısız oldu.', 'Analysis is unavailable.':'Analiz kullanılamıyor.',
};
export function translate(language: Language, text: string): string { return language === 'tr' ? tr[text] ?? text : text; }
const Context = createContext({ language: 'en' as Language, setLanguage: (_: Language) => {}, t: (text: string) => text });
export function LocaleProvider({children}: {children: ReactNode}) {
  const [language, setLanguage] = useState<Language>(() => { try { return initialLanguage(localStorage.getItem(key)); } catch { return 'en'; } });
  useEffect(() => { document.documentElement.lang = language; try { localStorage.setItem(key, language); } catch { /* Session preference still works. */ } }, [language]);
  return <Context.Provider value={{language, setLanguage, t: text => translate(language, text)}}>{children}</Context.Provider>;
}
export const useLocale = () => useContext(Context);
export function LanguageSelect() {
  const {language, setLanguage} = useLocale();
  return <label className="local-language"><span className="local-sr-only">Language / Dil</span><select aria-label="Language / Dil" value={language} onChange={event => setLanguage(event.target.value as Language)}><option value="en">English</option><option value="tr">Türkçe</option></select></label>;
}
