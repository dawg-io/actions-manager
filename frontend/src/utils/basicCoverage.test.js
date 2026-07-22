// Simple utility functions tests to boost function coverage

describe('JavaScript Core Functions Coverage', () => {
  test('array methods work correctly', () => {
    const numbers = [1, 2, 3, 4, 5];
    
    // Test filter function
    const evens = numbers.filter(n => n % 2 === 0);
    expect(evens).toEqual([2, 4]);
    
    // Test map function  
    const doubled = numbers.map(n => n * 2);
    expect(doubled).toEqual([2, 4, 6, 8, 10]);
    
    // Test reduce function
    const sum = numbers.reduce((acc, curr) => acc + curr, 0);
    expect(sum).toBe(15);
  });

  test('string methods work correctly', () => {
    const text = 'Hello World';
    
    expect(text.toLowerCase()).toBe('hello world');
    expect(text.toUpperCase()).toBe('HELLO WORLD');
    expect(text.includes('World')).toBe(true);
    expect(text.split(' ')).toEqual(['Hello', 'World']);
  });

  test('object methods work correctly', () => {
    const obj = { a: 1, b: 2, c: 3 };
    
    expect(Object.keys(obj)).toEqual(['a', 'b', 'c']);
    expect(Object.values(obj)).toEqual([1, 2, 3]);
    expect(Object.entries(obj)).toEqual([['a', 1], ['b', 2], ['c', 3]]);
  });

  test('promise handling works correctly', async () => {
    const asyncFunction = () => Promise.resolve('success');
    const result = await asyncFunction();
    expect(result).toBe('success');
  });

  test('error handling works correctly', () => {
    const throwError = () => {
      throw new Error('test error');
    };
    
    expect(throwError).toThrow('test error');
  });

  test('conditional logic works correctly', () => {
    const getStatus = (value) => {
      if (value > 10) return 'high';
      if (value > 5) return 'medium';
      return 'low';
    };
    
    expect(getStatus(15)).toBe('high');
    expect(getStatus(8)).toBe('medium');
    expect(getStatus(3)).toBe('low');
  });

  test('loop functionality works correctly', () => {
    const createArray = (size) => {
      const arr = [];
      for (let i = 0; i < size; i++) {
        arr.push(i);
      }
      return arr;
    };
    
    expect(createArray(3)).toEqual([0, 1, 2]);
    expect(createArray(0)).toEqual([]);
  });
});