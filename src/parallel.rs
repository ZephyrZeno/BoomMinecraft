//! Bounded, dynamically scheduled work with deterministic result order.
use std::{
    sync::{
        OnceLock,
        atomic::{AtomicUsize, Ordering},
    },
    time::Instant,
};

use anyhow::{Result, ensure};
use serde::Serialize;

pub const MAX_JOBS: usize = 64;

pub fn recommended_jobs() -> usize {
    std::thread::available_parallelism().map_or(1, |n| n.get().saturating_sub(1).clamp(1, 8))
}

#[derive(Debug, Serialize)]
pub struct Work<T> {
    pub results: Vec<T>,
    pub workers: usize,
    pub elapsed_ms: u128,
}

pub fn ordered_map<T: Sync, R: Send + Sync>(
    items: &[T],
    jobs: usize,
    operation: impl Fn(usize, &T) -> R + Sync,
) -> Result<Work<R>> {
    ensure!(
        (1..=MAX_JOBS).contains(&jobs),
        "Worker budget must be 1..={MAX_JOBS}"
    );
    let started = Instant::now();
    let next = AtomicUsize::new(0);
    let slots: Vec<OnceLock<R>> = (0..items.len()).map(|_| OnceLock::new()).collect();
    let workers = jobs.min(items.len());
    std::thread::scope(|scope| -> Result<()> {
        let handles: Vec<_> = (0..workers)
            .map(|_| {
                scope.spawn(|| {
                    loop {
                        let index = next.fetch_add(1, Ordering::Relaxed);
                        let Some(item) = items.get(index) else { break };
                        // Each index has exactly one owner; results never pass through an unbounded queue.
                        let _ = slots[index].set(operation(index, item));
                    }
                })
            })
            .collect();
        let mut panicked = false;
        for handle in handles {
            panicked |= handle.join().is_err();
        }
        ensure!(
            !panicked,
            "A worker panicked; no partial result was published"
        );
        Ok(())
    })?;
    Ok(Work {
        results: slots
            .into_iter()
            .map(|slot| slot.into_inner().expect("worker completed"))
            .collect(),
        workers,
        elapsed_ms: started.elapsed().as_millis(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Barrier, Mutex};

    #[test]
    fn runs_on_multiple_threads_but_returns_input_order() {
        let barrier = Barrier::new(4);
        let threads = Mutex::new(std::collections::HashSet::new());
        let work = ordered_map(&(0..16).collect::<Vec<_>>(), 4, |index, value| {
            threads.lock().unwrap().insert(std::thread::current().id());
            if index < 4 {
                barrier.wait();
            }
            value * value
        })
        .unwrap();
        assert_eq!(threads.into_inner().unwrap().len(), 4);
        assert_eq!(work.results, (0..16).map(|n| n * n).collect::<Vec<_>>());
    }

    #[test]
    fn empty_input_invalid_budgets_and_panics_are_handled() {
        assert_eq!(
            ordered_map::<i32, i32>(&[], 4, |_, n| *n).unwrap().workers,
            0
        );
        assert!(ordered_map(&[1], 0, |_, n| *n).is_err());
        assert!(ordered_map(&[1], 65, |_, n| *n).is_err());
        assert!(ordered_map(&[1], 1, |_, _| -> i32 { panic!("test worker") }).is_err());
    }
}
