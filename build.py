#!/usr/bin/env python3
"""
Build script to generate static JSON files for race analysis
"""

import json
import os
import shutil


def parse_time(time_str):
    """Convert time string (MM:SS.S or H:MM:SS.S) to seconds"""
    if not time_str or time_str.strip() == '':
        return None

    try:
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except:
        return None
    return None


def load_raw_results(year):
    """Load raw results for a specific year"""
    results = []
    filename = f'data/results-{year}.txt'

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()

            # Skip header
            for line in lines[1:]:
                if not line.strip():
                    continue

                # Split by tabs
                parts = line.strip().split('\t')
                if len(parts) < 9:
                    continue

                try:
                    age = int(parts[4])
                    sex = parts[5]
                    division = parts[6] if len(parts) > 6 else ''
                    gun_time = parts[7]
                    div_place = parts[2] if len(parts) > 2 else ''

                    # Only process M and F with valid times
                    if sex in ['M', 'F']:
                        time_seconds = parse_time(gun_time)
                        if time_seconds:
                            results.append({
                                'name': parts[3],
                                'age': age,
                                'sex': sex,
                                'division': division,
                                'div_place': div_place,
                                'time_seconds': time_seconds,
                                'time_display': gun_time,
                                'year': year
                            })
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f"Warning: {filename} not found")

    return results


def get_fastest_at_each_age(runners):
    """For all-time analysis: keep only the fastest runner at each age"""
    if not runners:
        return []

    # Group by age and keep only the fastest at each age
    age_groups = {}
    for runner in runners:
        age = runner['age']
        if age not in age_groups or runner['time_seconds'] < age_groups[age]['time_seconds']:
            age_groups[age] = runner

    return list(age_groups.values())


def compute_pareto_front(runners):
    """Compute Pareto front for a set of runners"""
    if not runners:
        return []

    # Find the peak (fastest runner)
    fastest = min(runners, key=lambda x: x['time_seconds'])
    peak_age = fastest['age']

    # Sort by age
    sorted_runners = sorted(runners, key=lambda x: x['age'])

    # Split into before and after peak
    younger_than_peak = [r for r in sorted_runners if r['age'] < peak_age]
    at_or_older_than_peak = [r for r in sorted_runners if r['age'] >= peak_age]

    pareto = []

    # For younger ages: include if faster than all younger runners (times decreasing)
    best_time_so_far = float('inf')
    for runner in younger_than_peak:
        if runner['time_seconds'] < best_time_so_far:
            pareto.append(runner)
            best_time_so_far = runner['time_seconds']

    # For peak and older ages: include if faster than all older runners (times increasing)
    # Process from oldest to peak
    best_time_so_far = float('inf')
    older_pareto = []
    for runner in reversed(at_or_older_than_peak):
        if runner['time_seconds'] < best_time_so_far:
            older_pareto.append(runner)
            best_time_so_far = runner['time_seconds']

    # Add older_pareto in correct order (youngest to oldest)
    pareto.extend(reversed(older_pareto))

    return pareto


def build_year_data(year, all_time_years=None):
    """Build data for a specific year"""
    print(f"Building data for {year}...")

    results = load_raw_results(year)

    # Determine which years to include for all-time Pareto (all years up to and including current)
    if all_time_years is None:
        all_time_years = []
        if year == '2025':
            all_time_years = ['2023', '2024', '2025']
        elif year == '2024':
            all_time_years = ['2023', '2024']
        else:  # 2023
            all_time_years = ['2023']

    # Load all data for all-time Pareto
    all_time_male_results = []
    all_time_female_results = []

    for hist_year in all_time_years:
        hist_results = load_raw_results(hist_year)
        all_time_male_results.extend([r for r in hist_results if r['sex'] == 'M'])
        all_time_female_results.extend([r for r in hist_results if r['sex'] == 'F'])

    # Separate by sex
    male_results = [r for r in results if r['sex'] == 'M']
    female_results = [r for r in results if r['sex'] == 'F']

    male_pareto = compute_pareto_front(male_results)
    female_pareto = compute_pareto_front(female_results)

    # Compute all-time Pareto fronts
    male_all_time_pareto = []
    female_all_time_pareto = []
    if all_time_male_results:
        fastest_male_by_age = get_fastest_at_each_age(all_time_male_results)
        male_all_time_pareto = compute_pareto_front(fastest_male_by_age)
    if all_time_female_results:
        fastest_female_by_age = get_fastest_at_each_age(all_time_female_results)
        female_all_time_pareto = compute_pareto_front(fastest_female_by_age)

    # Find age group winners
    age_group_winners = []
    for result in results:
        if result['div_place'] == '1' and result['division']:
            age_group_winners.append({
                'name': result['name'],
                'age': result['age'],
                'sex': result['sex'],
                'division': result['division'],
                'time_display': result['time_display']
            })
    age_group_winners.sort(key=lambda x: (x['sex'], x['division']))

    # Create pareto winners list
    pareto_winners = []
    for r in male_pareto:
        pareto_winners.append({
            'name': r['name'],
            'age': r['age'],
            'sex': 'M',
            'time_display': r['time_display']
        })
    for r in female_pareto:
        pareto_winners.append({
            'name': r['name'],
            'age': r['age'],
            'sex': 'F',
            'time_display': r['time_display']
        })
    pareto_winners.sort(key=lambda x: (x['sex'], x['age']))

    # Format data for output
    male_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in male_results]

    female_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in female_results]

    male_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in male_pareto]

    female_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in female_pareto]

    # Format all-time Pareto data with year information
    male_all_time_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name'],
        'year': r.get('year', 'Unknown'),
        'is_current_year': r.get('year') == year
    } for r in male_all_time_pareto]

    female_all_time_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name'],
        'year': r.get('year', 'Unknown'),
        'is_current_year': r.get('year') == year
    } for r in female_all_time_pareto]

    return {
        'male_all': male_data,
        'female_all': female_data,
        'male_pareto': male_pareto_data,
        'female_pareto': female_pareto_data,
        'male_all_time_pareto': male_all_time_pareto_data,
        'female_all_time_pareto': female_all_time_pareto_data,
        'age_group_winners': age_group_winners,
        'pareto_winners': pareto_winners
    }


def build_all_time_data():
    """Build combined all-time data"""
    print("Building all-time data...")

    all_years = ['2023', '2024', '2025']
    all_results = []

    for year in all_years:
        year_results = load_raw_results(year)
        all_results.extend(year_results)

    # Detect duplicate names and add year suffix if needed
    name_year_counts = {}
    for result in all_results:
        name = result['name']
        if name not in name_year_counts:
            name_year_counts[name] = []
        name_year_counts[name].append(result['year'])

    # Add year to display name if person appears in multiple years
    for result in all_results:
        name = result['name']
        if len(set(name_year_counts[name])) > 1:
            result['display_name'] = f"{name} ({result['year']})"
        else:
            result['display_name'] = name

    # Separate by sex
    male_results = [r for r in all_results if r['sex'] == 'M']
    female_results = [r for r in all_results if r['sex'] == 'F']

    # Get fastest at each age then compute Pareto
    fastest_male_by_age = get_fastest_at_each_age(male_results)
    fastest_female_by_age = get_fastest_at_each_age(female_results)
    male_pareto = compute_pareto_front(fastest_male_by_age)
    female_pareto = compute_pareto_front(fastest_female_by_age)

    # Format data
    male_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in male_results]

    female_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in female_results]

    male_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in male_pareto]

    female_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in female_pareto]

    # Create Pareto winners list
    pareto_winners = []
    for r in male_pareto:
        pareto_winners.append({
            'name': r['display_name'],
            'age': r['age'],
            'sex': 'M',
            'time_display': r['time_display'],
            'year': r['year']
        })
    for r in female_pareto:
        pareto_winners.append({
            'name': r['display_name'],
            'age': r['age'],
            'sex': 'F',
            'time_display': r['time_display'],
            'year': r['year']
        })
    pareto_winners.sort(key=lambda x: (x['sex'], x['age']))

    return {
        'male_all': male_data,
        'female_all': female_data,
        'male_pareto': male_pareto_data,
        'female_pareto': female_pareto_data,
        'pareto_winners': pareto_winners
    }


def main():
    """Main build function"""
    print("Starting static site build...")

    # Create build directory
    os.makedirs('build', exist_ok=True)
    os.makedirs('build/data', exist_ok=True)

    # Build data for each year
    for year in ['2023', '2024', '2025']:
        data = build_year_data(year)
        with open(f'build/data/{year}.json', 'w') as f:
            json.dump(data, f)
        print(f"  ✓ Generated data/{year}.json")

    # Build all-time data
    all_time_data = build_all_time_data()
    with open('build/data/all-time.json', 'w') as f:
        json.dump(all_time_data, f)
    print(f"  ✓ Generated data/all-time.json")

    # Copy HTML files
    for filename in ['race_chart_2023.html', 'race_chart_2024.html',
                     'race_chart_2025.html', 'race_chart_all_time.html']:
        shutil.copy(filename, f'build/{filename}')
        print(f"  ✓ Copied {filename}")

    # Copy index
    shutil.copy('race_chart_2025.html', 'build/index.html')
    print(f"  ✓ Created index.html")

    print("\n✅ Build complete! Static site is in the 'build/' directory")
    print("\nTo serve locally:")
    print("  cd build && python3 -m http.server 8000")
    print("  Then open http://localhost:8000")


if __name__ == '__main__':
    main()
