import { useState } from 'react'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 text-gray-800 gap-4">
      <h1 className="text-4xl font-bold text-gray-900">Frontend Ready 🚀</h1>
      <p className="text-gray-500">React + Vite + Tailwind CSS</p>
      <button
        type="button"
        onClick={() => setCount((c) => c + 1)}
        className="px-4 py-2 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-700 transition-colors"
      >
        Count is {count}
      </button>
    </div>
  )
}

export default App
