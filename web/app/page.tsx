import SearchInterface from '@/components/SearchInterface';

export default function Home() {
  return (
    <div className="flex flex-col h-full">
      <header className="flex-shrink-0 bg-cod-navy text-white px-4 py-3 shadow-md">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex flex-col">
            <span className="font-bold text-base leading-tight tracking-tight">
              Expert Sources
            </span>
            <span className="text-cod-gold-light text-xs font-medium opacity-90">
              Courier Student News · College of DuPage
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <SearchInterface />
      </main>
    </div>
  );
}
