// 1. Объявление функции (компонента)
export default function Home() {
  
  // 2. Логика (тут мы будем писать код на JavaScript/TypeScript)
  const studentName = "Xelit"; 

  // 3. Возврат интерфейса (JSX - это смесь HTML и JavaScript)
  return (
  <main className="p-10 bg-gray-100 min-h-screen"> 
    <div className="bg-white p-6 rounded-lg shadow-md max-w-sm">
      <h1 className="text-2xl font-bold text-blue-600">Привет, {studentName}!</h1>
      <p className="text-gray-500 mt-2">Это начало для нашего AI-assistan.</p>
    </div>
  </main>
  );
}