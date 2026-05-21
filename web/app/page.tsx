import { isDbReady } from '@/lib/db';
import ChatInterface from '@/components/ChatInterface';

export const dynamic = 'force-dynamic';

export default async function Home() {
  const dbReady = isDbReady();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex-shrink-0 bg-cod-navy text-white px-4 py-3 shadow-md">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex flex-col">
              <span className="font-bold text-base leading-tight tracking-tight">
                Expert Sources
              </span>
              <span className="text-cod-gold-light text-xs font-medium opacity-90">
                Courier Student News · College of DuPage
              </span>
            </div>
          </div>
          <div className="text-xs text-blue-200 text-right hidden sm:block">
            <p>Faculty database</p>
            <p className={dbReady ? 'text-green-300' : 'text-red-300'}>
              {dbReady ? '● Ready' : '● Not indexed'}
            </p>
          </div>
        </div>
      </header>

      {/* Chat area */}
      <main className="flex-1 overflow-hidden">
        <ChatInterface dbReady={dbReady} />
      </main>
    </div>
  );
}
